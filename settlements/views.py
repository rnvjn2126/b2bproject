from decimal import Decimal
from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from accounting.views import owner_only
from dashboard.models import Customer
from invoicing.models import InvoiceDraft, IssuedInvoice

from .allocations import record_payment_allocation
from .balances import invoice_balances, unallocated_payments
from .forms import StatementFilter
from .models import PartyCreditProfile, PartyPayment, PaymentAllocation
from .operation_forms import AllocationForm, CreditProfileForm, InvoiceDueForm, MseReviewForm, PaymentForm
from .services import record_party_payment, set_invoice_due_date
from .terms import apply_credit_due_date, record_mse_deadline, save_credit_profile


def settlement_owner(view):
    @owner_only
    @never_cache
    @wraps(view)
    def guarded(request, workspace, *args, **kwargs):
        if workspace is None or not settings.INTERNAL_INVOICE_ISSUANCE:
            raise Http404
        return view(request, workspace, *args, **kwargs)
    return guarded


@settlement_owner
@require_GET
def statement(request, workspace):
    today = timezone.localdate()
    form = StatementFilter(request.GET or None, workspace=workspace, initial={"as_of": today})
    context = {"form": form}
    if form.is_bound and not form.is_valid():
        return render(request, "settlements/statement.html", context)
    data = form.cleaned_data if form.is_bound else {}
    as_of = data.get("as_of") or today
    scope = {f"{key}_id": data[key].pk for key in ("customer", "supplier") if data.get(key)}
    rows = invoice_balances(workspace, as_of, **scope)
    buckets = ("Current", "1–30", "31–60", "61–90", "Over 90", "No due date")
    ageing = {bucket: {"sales": Decimal(0), "purchase": Decimal(0)} for bucket in buckets}
    for row in rows:
        if row.outstanding > 0:
            ageing[row.bucket][row.invoice.kind] += row.outstanding
    profile = PartyCreditProfile.objects.filter(workspace=workspace, **scope).first() if scope else None
    context.update(as_of=as_of, rows=rows, ageing=ageing, payments=unallocated_payments(workspace, as_of, **scope),
                   today=today, profile=profile)
    return render(request, "settlements/statement.html", context)


@settlement_owner
@require_GET
def reminder(request, workspace, pk):
    today = timezone.localdate()
    rows = invoice_balances(workspace, today, invoice_id=pk)
    if not rows:
        raise Http404
    row = rows[0]
    invoice = row.invoice
    if invoice.kind != InvoiceDraft.Kind.SALES or row.outstanding <= 0 or not row.due_on or row.due_on >= today:
        raise Http404
    party = Customer.objects.filter(owner_id=workspace.owner_id, pk=invoice.draft.movement.sales_line.order.customer_id).first()
    if party is None:
        raise Http404
    draft = (
        f"Hello {invoice.snapshot['party']['name']},\n\n"
        f"Our records show INR {row.outstanding:.2f} due on invoice {invoice.number}, "
        f"with a due date of {row.due_on:%d %b %Y}. Please let us know the payment status "
        f"or share the reference if it has already been paid.\n\n{workspace.name}"
    )
    return render(request, "settlements/reminder.html", {
        "invoice": invoice, "draft": draft,
        "whatsapp": f"{party.whatsapp_chat_url}?{urlencode({'text': draft})}" if party.whatsapp_chat_url else "",
    })


@settlement_owner
@require_http_methods(["GET", "POST"])
def payment_create(request, workspace):
    form = PaymentForm(request.POST if request.method == "POST" else None,
                       workspace=workspace, initial={"posting_on": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            payment = record_party_payment(
                workspace, request.user, posting_on=data["posting_on"], amount=data["amount"],
                funds_ledger_id=data["funds_ledger"].pk, control_ledger_id=data["control_ledger"].pk,
                submission_key=data["submission_key"], customer_id=getattr(data["customer"], "pk", None),
                supplier_id=getattr(data["supplier"], "pk", None), external_reference=data["external_reference"],
                narration=data["narration"],
            )
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            return redirect("accounting:settlements:payment_detail", pk=payment.pk)
    return render(request, "settlements/action.html", {"form": form, "title": "Record receipt or payment"})


@settlement_owner
@require_GET
def payment_detail(request, workspace, pk):
    payment = get_object_or_404(
        PartyPayment.objects.select_related("journal__reversal", "customer", "supplier"),
        workspace=workspace, pk=pk,
    )
    entries = payment.allocations.select_related("invoice").order_by("posted_on", "pk")
    used = sum((entry.signed_amount for entry in entries), Decimal(0))
    return render(request, "settlements/payment.html", {
        "payment": payment, "entries": entries, "unassigned": payment.amount - used,
    })


@settlement_owner
@require_http_methods(["GET", "POST"])
def payment_allocate(request, workspace, pk, allocation_pk=None):
    payment = get_object_or_404(PartyPayment, workspace=workspace, pk=pk)
    original = (get_object_or_404(PaymentAllocation, payment=payment, pk=allocation_pk, reverses__isnull=True)
                if allocation_pk is not None else None)
    form = AllocationForm(request.POST if request.method == "POST" else None, workspace=workspace,
                          payment=payment, release=original is not None, initial={"posted_on": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            record_payment_allocation(
                workspace, request.user, payment_id=payment.pk,
                invoice_id=original.invoice_id if original else data["invoice"].pk,
                posted_on=data["posted_on"], amount=data["amount"], reason=data["reason"],
                submission_key=data["submission_key"], reverses_id=original.pk if original else None,
            )
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            return redirect("accounting:settlements:payment_detail", pk=payment.pk)
    title = "Release allocated funds" if original else "Allocate payment to invoice"
    return render(request, "settlements/action.html", {"form": form, "title": title, "payment": payment})


@settlement_owner
@require_http_methods(["GET", "POST"])
def credit_profile(request, workspace):
    form = CreditProfileForm(request.POST if request.method == "POST" else None, workspace=workspace)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            save_credit_profile(workspace, request.user, customer_id=getattr(data["customer"], "pk", None),
                                supplier_id=getattr(data["supplier"], "pk", None), credit_days=data["credit_days"],
                                credit_limit=data["credit_limit"])
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            return redirect("accounting:settlements:statement")
    return render(request, "settlements/action.html", {"form": form, "title": "Party credit terms"})


@settlement_owner
@require_http_methods(["GET", "POST"])
def invoice_terms(request, workspace, pk, mode):
    invoice = get_object_or_404(IssuedInvoice, workspace=workspace, pk=pk, journal__sealed=True)
    mse = mode == "mse"
    if mse and invoice.kind != InvoiceDraft.Kind.PURCHASE:
        raise Http404
    form_class = MseReviewForm if mse else InvoiceDueForm
    form = form_class(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            if mse:
                record_mse_deadline(workspace, request.user, invoice_id=invoice.pk, **data)
            elif data["use_default"]:
                apply_credit_due_date(workspace, request.user, invoice_id=invoice.pk)
            else:
                set_invoice_due_date(workspace, request.user, invoice_id=invoice.pk, due_on=data["due_on"])
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            return redirect("accounting:settlements:statement")
    title = "Record reviewed MSE deadline" if mse else "Record invoice due date"
    return render(request, "settlements/action.html", {"form": form, "title": title, "invoice": invoice})
