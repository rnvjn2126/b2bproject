from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction

from accounting.services import lock_books
from invoicing.models import IssuedInvoice

from .models import InvoiceDueDate


@transaction.atomic
def set_invoice_due_date(workspace, actor, *, invoice_id, due_on):
    """Record one contractual due date for a posted document."""
    lock_books(workspace, actor)
    invoice = IssuedInvoice.objects.filter(workspace=workspace, pk=invoice_id, journal__sealed=True).first()
    if invoice is None:
        raise ValidationError("Choose a posted invoice in this workspace.")
    earliest = invoice.supplier_invoice_date or invoice.posting_on
    if type(due_on) is not date or due_on < earliest:
        raise ValidationError("The due date cannot precede the invoice date.")
    previous = InvoiceDueDate.objects.filter(invoice=invoice).first()
    if previous:
        if previous.due_on != due_on:
            raise ValidationError("A due date is already recorded for this invoice.")
        return previous
    return InvoiceDueDate.objects.create(invoice=invoice, due_on=due_on, recorded_by=actor)
