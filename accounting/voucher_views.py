import uuid
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import BalanceForm, JournalLines, VoucherForm
from .models import FinancialYear, Journal, Ledger, VoucherDraft
from .services import approve_voucher, lock_books
from .views import owner_only


@owner_only
@require_GET
def vouchers(request, workspace):
    entries = VoucherDraft.objects.filter(workspace=workspace).select_related("journal")
    return render(request, "accounting/vouchers.html", {"page": Paginator(entries, 25).get_page(request.GET.get("page"))})


@owner_only
@require_http_methods(["GET", "POST"])
def voucher_edit(request, workspace, pk=None):
    if not workspace or not FinancialYear.objects.filter(workspace=workspace).exists():
        return redirect("accounting:home")
    draft = get_object_or_404(VoucherDraft, workspace=workspace, pk=pk) if pk else None
    if draft and draft.journal_id:
        return redirect("accounting:journal", pk=draft.journal_id)
    initial = {"date": timezone.localdate(), "submission_key": uuid.uuid4(), "kind": Journal.Kind.GENERAL, "revision": 1}
    rows = []
    if draft:
        initial = {key: getattr(draft, key) for key in ("date", "kind", "reference", "narration", "branch", "cost_centre", "revision")}
        initial["submission_key"] = draft.posting_key
        rows = [{"ledger": ledger, "side": side, "amount": amount} for ledger, side, amount in draft.allocations]
    data = request.POST if request.method == "POST" else None
    form = VoucherForm(data, initial=initial, workspace=workspace)
    lines = JournalLines(data, initial=rows, form_kwargs={"workspace": workspace}, prefix="lines")
    if request.method == "POST" and all([form.is_valid(), lines.is_valid()]):
        values = form.cleaned_data.copy()
        posting_key = values.pop("submission_key")
        revision = values.pop("revision")
        values["allocations"] = [[row["ledger"].pk, row["side"], str(row["amount"])] for row in lines.cleaned_data if row]
        with transaction.atomic():
            lock_books(workspace, request.user)
            if draft:
                current = VoucherDraft.objects.get(pk=draft.pk, workspace=workspace)
                if current.journal_id:
                    return redirect("accounting:journal", pk=current.journal_id)
                if posting_key != current.posting_key or revision != current.revision:
                    form.add_error(None, "Reload this voucher before saving it.")
                else:
                    for key, value in values.items():
                        setattr(current, key, value)
                    current.revision += 1
                    current.save(update_fields=[*values, "revision"])
                    return redirect("accounting:voucher", pk=current.pk)
            else:
                current, created = VoucherDraft.objects.get_or_create(
                    workspace=workspace, posting_key=posting_key, defaults={**values, "creator": request.user},
                )
                if created or all(getattr(current, key) == value for key, value in values.items()):
                    return redirect("accounting:voucher", pk=current.pk)
                form.add_error(None, "This submission key already belongs to a draft. Start a new voucher.")
    return render(request, "accounting/form.html", {
        "form": form, "lines": lines, "title": "Edit voucher draft" if draft else "New voucher draft",
        "submit": "Save draft", "note": "Drafts do not affect the ledger. Review allocations before approving.",
    })


@owner_only
@require_GET
def voucher_detail(request, workspace, pk):
    draft = get_object_or_404(VoucherDraft, workspace=workspace, pk=pk)
    if draft.journal_id:
        return redirect("accounting:journal", pk=draft.journal_id)
    ledgers = Ledger.objects.filter(workspace=workspace).in_bulk(row[0] for row in draft.allocations)
    rows = [(ledgers.get(ledger), side, Decimal(amount)) for ledger, side, amount in draft.allocations]
    return render(request, "accounting/voucher.html", {
        "draft": draft, "rows": rows,
        "debit": sum((amount for _, side, amount in rows if side == "D"), Decimal(0)),
        "credit": sum((amount for _, side, amount in rows if side == "C"), Decimal(0)),
    })


@owner_only
@require_POST
def voucher_approve(request, workspace, pk):
    draft = get_object_or_404(VoucherDraft, workspace=workspace, pk=pk)
    try:
        revision = int(request.POST.get("revision", ""))
    except ValueError:
        return HttpResponseBadRequest("A voucher revision is required.")
    try:
        journal = approve_voucher(workspace, request.user, draft.pk, revision)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("accounting:voucher", pk=pk)
    messages.success(request, "Voucher approved and posted.")
    return redirect("accounting:journal", pk=journal.pk)


@owner_only
@require_GET
def day_book(request, workspace):
    today = timezone.localdate()
    form = BalanceForm(request.GET or {"start": today, "end": today}, workspace=workspace)
    entries = Journal.objects.none()
    if form.is_valid():
        entries = Journal.objects.filter(
            workspace=workspace, sealed=True, date__range=(form.cleaned_data["start"], form.cleaned_data["end"]),
        ).select_related("branch").prefetch_related("lines").order_by("date", "pk")
        if form.cleaned_data["branch"]:
            entries = entries.filter(branch=form.cleaned_data["branch"])
    page = Paginator(entries, 25).get_page(request.GET.get("page"))
    rows = []
    for journal in page:
        debit = sum((line.amount for line in journal.lines.all() if line.side == "D"), Decimal(0))
        credit = sum((line.amount for line in journal.lines.all() if line.side == "C"), Decimal(0))
        rows.append((journal, debit, credit))
    return render(request, "accounting/day_book.html", {"form": form, "page": page, "rows": rows})
