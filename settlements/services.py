from datetime import date
from uuid import NAMESPACE_URL, UUID, uuid5

from django.core.exceptions import ValidationError
from django.db import transaction

from accounting.models import AccountGroup, Journal, Ledger
from accounting.services import funds_ledgers, lock_books, post_journal
from dashboard.models import Customer, Supplier
from invoicing.models import IssuedInvoice
from invoicing.tax import check_decimal

from .models import InvoiceDueDate, PartyPayment


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


@transaction.atomic
def record_party_payment(workspace, actor, *, posting_on, amount, funds_ledger_id, control_ledger_id,
                         submission_key, customer_id=None, supplier_id=None, external_reference="", narration=""):
    """Post a receipt or supplier payment and preserve its party and bank/cash linkage."""
    lock_books(workspace, actor)
    if (customer_id is None) == (supplier_id is None):
        raise ValidationError("Choose either a customer or a supplier.")
    receipt = customer_id is not None
    party_model, party_id = (Customer, customer_id) if receipt else (Supplier, supplier_id)
    party = party_model.objects.filter(pk=party_id, owner_id=workspace.owner_id).first()
    if party is None:
        raise ValidationError("Choose a party in your workspace.")
    check_decimal(amount, 15, 2)
    if amount <= 0 or type(posting_on) is not date:
        raise ValidationError("Enter a positive amount and a valid posting date.")
    if not isinstance(submission_key, UUID) or not isinstance(external_reference, str) or not isinstance(narration, str):
        raise ValidationError("Enter a valid payment reference, narration and submission key.")
    external_reference = external_reference.strip().upper()
    narration = narration.strip() or ("Customer receipt" if receipt else "Supplier payment")
    if len(external_reference) > 100 or len(narration) > 500:
        raise ValidationError("The payment reference or narration is too long.")
    expected_party = {"customer_id": customer_id, "supplier_id": supplier_id}
    existing = PartyPayment.objects.filter(workspace=workspace, submission_key=submission_key).select_related("journal").first()
    if existing:
        prior = (existing.customer_id, existing.supplier_id, existing.amount, existing.funds_ledger_id,
                 existing.control_ledger_id, existing.journal.date, existing.external_reference, existing.journal.narration)
        requested = (customer_id, supplier_id, amount, funds_ledger_id, control_ledger_id, posting_on,
                     external_reference, narration)
        if prior != requested:
            raise ValidationError("This submission key already belongs to a different payment.")
        return existing

    choices = Ledger.objects.filter(workspace=workspace, group__workspace=workspace).select_related("group")
    funds_choices = funds_ledgers(workspace)
    funds = funds_choices.select_related("group").filter(pk=funds_ledger_id).first()
    expected_kind = AccountGroup.Kind.ASSET if receipt else AccountGroup.Kind.LIABILITY
    control = choices.filter(pk=control_ledger_id, group__kind=expected_kind).exclude(pk__in=funds_choices).first()
    if not funds or not control:
        raise ValidationError("Choose a cash or bank ledger and the correct party control ledger in this workspace.")
    if external_reference and PartyPayment.objects.filter(
        workspace=workspace, funds_ledger=funds, external_reference=external_reference,
    ).exists():
        raise ValidationError("This payment reference is already recorded for the funds ledger.")
    kind = Journal.Kind.RECEIPT if receipt else Journal.Kind.PAYMENT
    lines = ((funds, "D", amount), (control, "C", amount)) if receipt else ((control, "D", amount), (funds, "C", amount))
    journal = post_journal(
        workspace, actor, date=posting_on, kind=kind, reference=external_reference, narration=narration,
        submission_key=uuid5(NAMESPACE_URL, f"steel-quotes/party-payment/{workspace.pk}/{submission_key}"), lines=lines,
    )
    return PartyPayment.objects.create(
        workspace=workspace, journal=journal, funds_ledger=funds, control_ledger=control, amount=amount,
        external_reference=external_reference, submission_key=submission_key, **expected_party,
    )
