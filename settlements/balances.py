from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Prefetch

from invoicing.models import InvoiceReturn, IssuedInvoice

from .models import PartyPayment, PaymentAllocation


@dataclass(frozen=True)
class InvoiceBalance:
    invoice: IssuedInvoice
    due_on: date | None
    adjusted_total: Decimal
    allocated: Decimal
    outstanding: Decimal
    bucket: str


def ageing_bucket(due_on, as_of):
    if due_on is None:
        return "No due date"
    days = (as_of - due_on).days
    if days <= 0:
        return "Current"
    for maximum, label in ((30, "1–30"), (60, "31–60"), (90, "61–90")):
        if days <= maximum:
            return label
    return "Over 90"


def invoice_balances(workspace, as_of, *, invoice_id=None, customer_id=None, supplier_id=None):
    """Project sealed invoice amounts as of a date, net of posted corrections."""
    if type(as_of) is not date:
        raise ValidationError("Choose an as-of date.")
    returns = InvoiceReturn.objects.filter(
        journal__date__lte=as_of, journal__sealed=True, journal__workspace=workspace,
    )
    invoices = IssuedInvoice.objects.filter(
        workspace=workspace, journal__workspace=workspace, journal__sealed=True, posting_on__lte=as_of,
    )
    if invoice_id is not None:
        invoices = invoices.filter(pk=invoice_id)
    if customer_id is not None:
        invoices = invoices.filter(draft__movement__sales_line__order__customer_id=customer_id)
    if supplier_id is not None:
        invoices = invoices.filter(draft__movement__purchase_order__supplier_id=supplier_id)
    invoices = invoices.select_related("due_date", "mse_deadline", "cancellation__reversal").prefetch_related(
        Prefetch("returns", queryset=returns, to_attr="posted_returns"),
        Prefetch("allocations", queryset=active_allocations(workspace, as_of), to_attr="posted_allocations"),
    ).order_by("posting_on", "id")
    rows = []
    for invoice in invoices:
        due_on = invoice.due_date.due_on if hasattr(invoice, "due_date") else None
        cancellation = getattr(invoice, "cancellation", None)
        if (cancellation and cancellation.reversal.workspace_id == workspace.pk
                and cancellation.reversal.sealed and cancellation.reversal.date <= as_of):
            adjusted = Decimal(0)
        else:
            adjusted = invoice.total - sum((entry.amount for entry in invoice.posted_returns), Decimal(0))
        allocated = sum((entry.signed_amount for entry in invoice.posted_allocations), Decimal(0))
        rows.append(InvoiceBalance(invoice, due_on, adjusted, allocated, adjusted - allocated, ageing_bucket(due_on, as_of)))
    return rows


def active_payments(workspace, as_of):
    return PartyPayment.objects.filter(
        workspace=workspace, journal__workspace=workspace, journal__sealed=True, journal__date__lte=as_of,
    ).exclude(journal__reversal__sealed=True, journal__reversal__date__lte=as_of)


def active_allocations(workspace, as_of):
    return PaymentAllocation.objects.filter(
        payment__in=active_payments(workspace, as_of), invoice__workspace=workspace, posted_on__lte=as_of,
    )


def unallocated_payments(workspace, as_of, *, customer_id=None, supplier_id=None):
    payments = active_payments(workspace, as_of)
    if customer_id is not None:
        payments = payments.filter(customer_id=customer_id)
    if supplier_id is not None:
        payments = payments.filter(supplier_id=supplier_id)
    payments = payments.prefetch_related(
        Prefetch("allocations", queryset=active_allocations(workspace, as_of), to_attr="posted_allocations"),
    ).select_related("journal", "customer", "supplier").order_by("journal__date", "id")
    return [(payment, payment.amount - sum((entry.signed_amount for entry in payment.posted_allocations), Decimal(0)))
            for payment in payments]
