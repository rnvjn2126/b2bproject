import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Case, F, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from dashboard.accounts import business_account_for

from .forms import BalanceForm, CashVoucherForm, ChartForm, GroupForm, JournalForm, JournalLines, LedgerForm, PostingForm, YearForm
from .models import AccountGroup, Branch, CostCentre, FinancialYear, Journal, JournalLine, Ledger, Period
from .services import lock_books, lock_period, post_journal, setup_books
from .statements import financial_statements


def owner_only(view):
    @login_required
    @wraps(view)
    def scoped(request, *args, **kwargs):
        workspace = business_account_for(request.user)
        if workspace and workspace.owner_id != request.user.pk:
            raise PermissionDenied("Only the workspace owner can access the accounting books.")
        return view(request, workspace, *args, **kwargs)
    return scoped


def financial_year_start(today):
    return today.year if today.month >= 4 else today.year - 1


@owner_only
@require_http_methods(["GET", "POST"])
def home(request, workspace):
    form = YearForm(request.POST if request.method == "POST" else None, initial={
        "start_year": financial_year_start(timezone.localdate()),
    })
    if request.method == "POST" and form.is_valid():
        workspace = workspace or business_account_for(request.user, create=True)
        setup_books(workspace, request.user, form.cleaned_data["start_year"])
        messages.success(request, "Financial year and starter chart are ready.")
        return redirect("accounting:home")
    return render(request, "accounting/home.html", {
        "form": form, "years": FinancialYear.objects.filter(workspace=workspace).prefetch_related("periods"),
        "inventory_enabled": workspace is not None and settings.INTERNAL_INVENTORY,
    })


@owner_only
@require_POST
def close_period(request, workspace, pk):
    period = get_object_or_404(Period, pk=pk, year__workspace=workspace)
    if lock_period(workspace, request.user, period.pk):
        messages.success(request, "Period locked.")
    return redirect("accounting:home")


@owner_only
@require_GET
def chart(request, workspace):
    return render(request, "accounting/chart.html", {
        "groups": AccountGroup.objects.filter(workspace=workspace).select_related("parent"),
        "ledgers": Ledger.objects.filter(workspace=workspace).select_related("group"),
        "branches": Branch.objects.filter(workspace=workspace),
        "centres": CostCentre.objects.filter(workspace=workspace),
    })


@owner_only
@require_http_methods(["GET", "POST"])
def add_chart_record(request, workspace, kind):
    if workspace is None or not FinancialYear.objects.filter(workspace=workspace).exists():
        return redirect("accounting:home")
    model, form_class, label = {
        "group": (AccountGroup, GroupForm, "account group"),
        "ledger": (Ledger, LedgerForm, "ledger"),
        "branch": (Branch, ChartForm, "branch"),
        "cost-centre": (CostCentre, ChartForm, "cost centre"),
    }[kind]
    kwargs = {"workspace": workspace} if form_class in (GroupForm, LedgerForm) else {}
    form = form_class(request.POST if request.method == "POST" else None, **kwargs)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            lock_books(workspace, request.user)
            _, created = model.objects.get_or_create(workspace=workspace, code=data["code"], defaults=data)
        if created:
            return redirect("accounting:chart")
        form.add_error("code", "This code already exists in the workspace.")
    return render(request, "accounting/form.html", {"form": form, "title": f"Add {label}", "submit": "Save"})


@owner_only
@require_GET
def journals(request, workspace):
    entries = Journal.objects.filter(workspace=workspace, sealed=True).select_related("branch")
    return render(request, "accounting/journals.html", {"page": Paginator(entries, 25).get_page(request.GET.get("page"))})


@owner_only
@require_GET
def audit_history(request, workspace):
    journals = Journal.objects.filter(workspace=workspace, sealed=True).order_by().annotate(
        event_time=F("posted_at"), actor=F("submitted_by__username"),
        event=Case(When(kind=Journal.Kind.REVERSAL, then=Value("Journal reversed")), default=Value("Journal posted")),
        object_id=F("pk"), event_date=F("date"),
    ).values("event_time", "actor", "event", "object_id", "event_date")
    locks = Period.objects.filter(year__workspace=workspace, locked_at__isnull=False).order_by().annotate(
        event_time=F("locked_at"), actor=F("locked_by__username"), event=Value("Period locked"),
        object_id=F("pk"), event_date=F("starts_on"),
    ).values("event_time", "actor", "event", "object_id", "event_date")
    events = journals.union(locks).order_by("-event_time", "event", "-object_id")
    return render(request, "accounting/audit_history.html", {
        "page": Paginator(events, 25).get_page(request.GET.get("page")),
    })


@owner_only
@require_GET
def journal_detail(request, workspace, pk):
    journal = get_object_or_404(Journal.objects.select_related("branch", "cost_centre", "submitted_by", "reverses", "reversal"),
                               workspace=workspace, pk=pk, sealed=True)
    return render(request, "accounting/journal.html", {"journal": journal, "lines": journal.lines.select_related("ledger")})


@owner_only
@require_http_methods(["GET", "POST"])
def journal_create(request, workspace):
    if workspace is None:
        return redirect("accounting:home")
    data = request.POST if request.method == "POST" else None
    form = JournalForm(data, workspace=workspace, initial={
        "date": timezone.localdate(), "submission_key": uuid.uuid4(), "kind": Journal.Kind.GENERAL,
    })
    lines = JournalLines(data, prefix="lines", form_kwargs={"workspace": workspace})
    if request.method == "POST" and form.is_valid() and lines.is_valid():
        entries = [(row["ledger"], row["side"], row["amount"]) for row in lines.cleaned_data if row]
        try:
            journal = post_journal(workspace, request.user, lines=entries, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Journal posted.")
            return redirect("accounting:journal", pk=journal.pk)
    return render(request, "accounting/form.html", {"form": form, "lines": lines, "title": "Post journal", "submit": "Post journal"})


@owner_only
@require_http_methods(["GET", "POST"])
def cash_voucher_create(request, workspace, kind):
    if workspace is None or not FinancialYear.objects.filter(workspace=workspace).exists():
        return redirect("accounting:home")
    form = CashVoucherForm(request.POST if request.method == "POST" else None, workspace=workspace, kind=kind,
                           initial={"date": timezone.localdate(), "submission_key": uuid.uuid4()})
    if request.method == "POST" and form.is_valid():
        debits, credits, amount = (form.cleaned_data[field] for field in ("debit", "credit", "amount"))
        fields = {key: value for key, value in form.cleaned_data.items() if key not in ("debit", "credit", "amount")}
        try:
            journal = post_journal(workspace, request.user, kind=kind,
                                   lines=[(debits, "D", amount), (credits, "C", amount)], **fields)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Voucher posted.")
            return redirect("accounting:journal", pk=journal.pk)
    return render(request, "accounting/form.html", {
        "form": form, "title": kind.label, "submit": "Post voucher",
        "note": "Record a movement already confirmed in your books. Choose the ledgers and enter the INR amount.",
    })


@owner_only
@require_http_methods(["GET", "POST"])
def reverse_journal(request, workspace, pk):
    original = get_object_or_404(Journal, workspace=workspace, pk=pk, sealed=True)
    form = PostingForm(request.POST if request.method == "POST" else None, initial={
        "date": timezone.localdate(), "reference": original.reference, "submission_key": uuid.uuid4(),
    })
    if request.method == "POST" and form.is_valid():
        try:
            journal = post_journal(workspace, request.user, reverses=original, kind=Journal.Kind.REVERSAL, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            return redirect("accounting:journal", pk=journal.pk)
    return render(request, "accounting/form.html", {
        "form": form, "title": f"Reverse journal {original.pk}", "submit": "Post reversal",
        "note": "The reversal posts opposite entries. Choose an open accounting period and enter the reason.",
    })


@owner_only
@require_GET
def balances(request, workspace, pk=None):
    ledger = get_object_or_404(Ledger, workspace=workspace, pk=pk) if pk else None
    today = timezone.localdate()
    defaults = {"start": date(financial_year_start(today), 4, 1), "end": today}
    form = BalanceForm(request.GET or defaults, workspace=workspace)
    rows, detail, totals = [], None, None
    if form.is_valid():
        start, end, branch = (form.cleaned_data[key] for key in ("start", "end", "branch"))
        entries = JournalLine.objects.filter(journal__workspace=workspace, journal__sealed=True,
                                             ledger__workspace=workspace, journal__date__lte=end)
        if branch:
            entries = entries.filter(journal__branch=branch)
        if ledger:
            entries = entries.filter(ledger=ledger)

        # Sum stored Decimals in Python so SQLite's floating-point SUM cannot affect totals.
        amounts = defaultdict(lambda: [Decimal(0), Decimal(0), Decimal(0)])
        for ledger_id, posting_date, side, amount in entries.order_by().values_list(
            "ledger_id", "journal__date", "side", "amount",
        ).iterator():
            slot = amounts[ledger_id]
            if posting_date < start:
                slot[0] += amount if side == "D" else -amount
            else:
                slot[1 if side == "D" else 2] += amount
        totals = dict.fromkeys(("debit", "credit", "closing_debit", "closing_credit"), Decimal(0))
        for account in Ledger.objects.filter(workspace=workspace, pk__in=amounts):
            opening, debit, credit = amounts[account.pk]
            closing = opening + debit - credit
            row = {"ledger": account, "opening": opening, "debit": debit, "credit": credit,
                   "closing_debit": max(closing, Decimal(0)), "closing_credit": max(-closing, Decimal(0))}
            rows.append(row)
            for key in totals:
                totals[key] += row[key]
        if ledger:
            detail = Paginator(entries.filter(journal__date__gte=start).select_related("journal")
                               .order_by("journal__date", "journal_id", "pk"), 50).get_page(request.GET.get("page"))
    return render(request, "accounting/balances.html", {
        "form": form, "rows": rows, "detail": detail, "ledger": ledger, "totals": totals,
    })


@owner_only
@require_GET
def statements(request, workspace):
    today = timezone.localdate()
    defaults = {"start": date(financial_year_start(today), 4, 1), "end": today}
    form = BalanceForm(request.GET or defaults, workspace=workspace)
    result = financial_statements(workspace, **form.cleaned_data) if workspace and form.is_valid() else None
    return render(request, "accounting/statements.html", {
        "form": form, "statements": result, "workspace": workspace,
    })
