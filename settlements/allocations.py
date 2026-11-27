from datetime import date
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from accounting.models import Journal, Period
from accounting.services import lock_books
from invoicing.models import IssuedInvoice
from invoicing.tax import check_decimal

from .balances import active_payments, invoice_balances
from .models import PartyPayment, PaymentAllocation


@transaction.atomic
def record_payment_allocation(workspace, actor, *, payment_id, invoice_id, posted_on, amount,
                              submission_key, reverses_id=None, reason=""):
    """Assign or release party funds without changing the sealed cash journal."""
    lock_books(workspace, actor)
    payment = PartyPayment.objects.filter(workspace=workspace, pk=payment_id, journal__sealed=True).select_related("journal").first()
    invoice = IssuedInvoice.objects.filter(workspace=workspace, pk=invoice_id, journal__sealed=True).select_related(
        "draft__movement__sales_line__order", "draft__movement__purchase_order", "cancellation__reversal",
    ).first()
    if not payment or not invoice:
        raise ValidationError("Choose a posted payment and invoice in your workspace.")
    check_decimal(amount, 15, 2)
    if amount <= 0 or type(posted_on) is not date or not isinstance(submission_key, UUID):
        raise ValidationError("Enter a positive allocation, posting date and submission key.")
    if not isinstance(reason, str) or len(reason.strip()) > 250 or (reverses_id is not None and not reason.strip()):
        raise ValidationError("Enter a reason of up to 250 characters for an allocation adjustment.")
    reason = reason.strip()

    existing = payment.allocations.filter(submission_key=submission_key).first()
    if existing:
        if (existing.invoice_id, existing.posted_on, existing.amount, existing.reverses_id, existing.reason) != (
            invoice_id, posted_on, amount, reverses_id, reason,
        ):
            raise ValidationError("This submission key already belongs to a different allocation.")
        return existing

    movement = invoice.draft.movement
    if payment.customer_id:
        matches = movement.sales_line_id and movement.sales_line.order.customer_id == payment.customer_id
        role = "receivable"
    else:
        matches = movement.purchase_order_id and movement.purchase_order.supplier_id == payment.supplier_id
        role = "payable"
    if not matches or invoice.ledger_ids.get(role) != payment.control_ledger_id:
        raise ValidationError("The payment and invoice must have the same party and control ledger.")
    today = timezone.localdate()
    if not active_payments(workspace, today).filter(pk=payment.pk).exists():
        raise ValidationError("This payment is not available for allocation.")
    if not max(invoice.posting_on, payment.journal.date) <= posted_on <= today or not Period.objects.filter(
        year__workspace=workspace, starts_on__lte=posted_on, ends_before__gt=posted_on, locked_at__isnull=True,
    ).exists():
        raise ValidationError("Use an open accounting date on or after the invoice and payment.")
    latest_allocation = PaymentAllocation.objects.filter(Q(payment=payment) | Q(invoice=invoice)).aggregate(
        last=Max("posted_on"),
    )["last"]
    latest_reversal = Journal.objects.filter(
        workspace=workspace, sealed=True, reverses__partypayment__allocations__invoice=invoice,
    ).aggregate(last=Max("date"))["last"]
    latest_return = invoice.returns.aggregate(last=Max("journal__date"))["last"]
    cancellation = getattr(invoice, "cancellation", None)
    latest_event = max(value for value in (
        invoice.posting_on, latest_allocation, latest_reversal, latest_return,
        cancellation.reversal.date if cancellation else None,
    ) if value is not None)
    if posted_on < latest_event:
        raise ValidationError("The allocation date cannot precede a later invoice or payment event.")

    original = None
    if reverses_id is not None:
        original = payment.allocations.filter(pk=reverses_id, invoice=invoice, reverses__isnull=True).first()
        if original is None or amount + sum((row.amount for row in original.adjustments.all()), Decimal(0)) > original.amount:
            raise ValidationError("The adjustment exceeds the original allocation.")
    else:
        unassigned = payment.amount - sum((row.signed_amount for row in payment.allocations.all()), Decimal(0))
        balance, = invoice_balances(workspace, posted_on, invoice_id=invoice.pk)
        if amount > unassigned or amount > balance.outstanding:
            raise ValidationError("The allocation exceeds either available funds or the invoice balance.")
    return PaymentAllocation.objects.create(
        payment=payment, invoice=invoice, reverses=original, posted_on=posted_on,
        amount=amount, reason=reason, submission_key=submission_key, recorded_by=actor,
    )
