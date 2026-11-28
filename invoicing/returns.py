from datetime import date
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounting.models import Journal
from accounting.services import lock_books, post_journal
from inventory.sale_costs import apply_sale_cost_correction

from .models import InvoiceDraft, InvoiceReturn, IssuedInvoice
from .tax import check_decimal, rounded


@transaction.atomic
def record_invoice_return(workspace, actor, *, invoice_id, posting_on, quantity, reason, submission_key, restock_movement_id=None):
    """Post a financial return and restore cost only for an explicitly linked restock receipt."""
    if not settings.INTERNAL_INVOICE_ISSUANCE:
        raise PermissionDenied("Internal invoice issuance is disabled.")
    lock_books(workspace, actor)
    invoice = IssuedInvoice.objects.filter(workspace=workspace, pk=invoice_id).select_related("journal").first()
    if invoice is None:
        raise ValidationError("Choose an issued invoice in your workspace.")
    check_decimal(quantity, 14, 3)
    if quantity <= 0:
        raise ValidationError("Enter a positive return quantity.")
    if type(posting_on) is not date or posting_on < invoice.posting_on:
        raise ValidationError("The return date cannot precede the invoice posting.")
    if not isinstance(submission_key, UUID) or not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
        raise ValidationError("Enter a return reason and a valid submission key.")
    reason = reason.strip()
    previous = list(invoice.returns.select_related("journal").order_by("sequence"))
    for entry in previous:
        if entry.submission_key == submission_key:
            if (entry.quantity, entry.journal.date, entry.reason) != (quantity, posting_on, reason):
                raise ValidationError("This submission already belongs to a different return.")
            return apply_sale_cost_correction(workspace, actor, entry, restock_movement_id)
    if hasattr(invoice, "cancellation"):
        raise ValidationError("A cancelled invoice cannot receive returns.")
    if previous and posting_on < previous[-1].journal.date:
        raise ValidationError("The return date cannot precede the last return.")

    original_quantity = Decimal(invoice.snapshot["item"]["quantity"])
    check_decimal(original_quantity, 14, 3)
    returned = sum((entry.quantity for entry in previous), Decimal(0))
    if original_quantity <= 0 or returned + quantity > original_quantity:
        raise ValidationError("The return quantity exceeds the remaining invoiced quantity.")

    sales = invoice.kind == InvoiceDraft.Kind.SALES
    control_ledger_id = invoice.ledger_ids["receivable" if sales else "payable"]
    original_lines = list(invoice.journal.lines.select_related("ledger__group"))
    control = next((line for line in original_lines if line.ledger_id == control_ledger_id), None)
    if control is None:
        raise ValidationError("The invoice is missing its original control ledger.")
    lines = []
    amount = Decimal(0)
    # Round each component cumulatively so a full return reverses every original paise.
    for line in original_lines:
        if line == control:
            continue
        delta = rounded(line.amount * (returned + quantity) / original_quantity) - rounded(
            line.amount * returned / original_quantity,
        )
        if delta:
            lines.append((line.ledger, "C" if line.side == "D" else "D", delta))
            amount += delta if line.side != control.side else -delta
    if amount <= 0:
        raise ValidationError("The return quantity is too small to record a positive financial adjustment.")
    if amount + sum((entry.amount for entry in previous), Decimal(0)) > invoice.total:
        raise ValidationError("The financial adjustment exceeds the remaining invoice amount.")
    lines.insert(0, (control.ledger, "C" if control.side == "D" else "D", amount))
    sequence = len(previous) + 1
    kind = Journal.Kind.SALES_RETURN if sales else Journal.Kind.PURCHASE_RETURN
    journal = post_journal(
        workspace, actor, date=posting_on, kind=kind, reference=f"{invoice.number}-{'CN' if sales else 'DN'}-{sequence}",
        narration=reason, submission_key=uuid5(NAMESPACE_URL, f"steel-quotes/return/{invoice.pk}/{submission_key}"),
        lines=lines,
    )
    correction = InvoiceReturn.objects.create(
        invoice=invoice, journal=journal, sequence=sequence, submission_key=submission_key,
        quantity=quantity, amount=amount, reason=reason, recorded_by=actor,
    )
    return apply_sale_cost_correction(workspace, actor, correction, restock_movement_id)
