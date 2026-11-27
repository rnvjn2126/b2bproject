from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounting.services import lock_books
from dashboard.models import Customer, Supplier
from invoicing.models import InvoiceDraft, IssuedInvoice
from invoicing.tax import check_decimal

from .balances import invoice_balances
from .models import MsePaymentDeadline, PartyCreditProfile
from .services import set_invoice_due_date


@transaction.atomic
def save_credit_profile(workspace, actor, *, customer_id=None, supplier_id=None, credit_days, credit_limit=None):
    lock_books(workspace, actor)
    if (customer_id is None) == (supplier_id is None) or type(credit_days) is not int or not 0 <= credit_days <= 365:
        raise ValidationError("Choose one party and a credit period between zero and 365 days.")
    if credit_limit is not None:
        check_decimal(credit_limit, 15, 2)
        if credit_limit < 0:
            raise ValidationError("The credit limit cannot be negative.")
    model, party_id = (Customer, customer_id) if customer_id is not None else (Supplier, supplier_id)
    if not model.objects.filter(pk=party_id, owner_id=workspace.owner_id).exists():
        raise ValidationError("Choose a party in this workspace.")
    profile, _ = PartyCreditProfile.objects.update_or_create(
        workspace=workspace, customer_id=customer_id, supplier_id=supplier_id,
        defaults={"credit_days": credit_days, "credit_limit": credit_limit},
    )
    return profile


@transaction.atomic
def apply_credit_due_date(workspace, actor, *, invoice_id):
    lock_books(workspace, actor)
    invoice = IssuedInvoice.objects.filter(workspace=workspace, pk=invoice_id, journal__sealed=True).select_related(
        "draft__movement__sales_line__order", "draft__movement__purchase_order",
    ).first()
    if not invoice:
        raise ValidationError("Choose a posted invoice in this workspace.")
    movement = invoice.draft.movement
    party = ({"customer_id": movement.sales_line.order.customer_id} if invoice.kind == InvoiceDraft.Kind.SALES
             else {"supplier_id": movement.purchase_order.supplier_id})
    profile = PartyCreditProfile.objects.filter(workspace=workspace, **party).first()
    if not profile:
        raise ValidationError("Set a contractual credit period for this party first.")
    due_on = (invoice.supplier_invoice_date or invoice.posting_on) + timedelta(days=profile.credit_days)
    return set_invoice_due_date(workspace, actor, invoice_id=invoice.pk, due_on=due_on)


@dataclass(frozen=True)
class CreditExposure:
    posted_due: Decimal
    overdue: Decimal
    limit: Decimal | None
    projected: Decimal

    @property
    def exceeds_limit(self):
        return self.limit is not None and self.projected > self.limit


def customer_credit_exposure(workspace, *, customer_id, proposed_total, as_of):
    """Conservatively measure positive posted receivables for an internal warning."""
    check_decimal(proposed_total, 15, 2)
    if proposed_total < 0:
        raise ValidationError("The proposed invoice amount cannot be negative.")
    profile = PartyCreditProfile.objects.filter(workspace=workspace, customer_id=customer_id).first()
    rows = [row for row in invoice_balances(workspace, as_of, customer_id=customer_id) if row.outstanding > 0]
    posted = sum((row.outstanding for row in rows), Decimal(0))
    overdue = sum((row.outstanding for row in rows if row.due_on and row.due_on < as_of), Decimal(0))
    return CreditExposure(posted, overdue, profile.credit_limit if profile else None, posted + proposed_total)


@transaction.atomic
def record_mse_deadline(workspace, actor, *, invoice_id, eligibility_reviewed, accepted_on,
                        written_due_on=None, evidence_reference):
    """Record an opt-in Section 15 tracking date using independently confirmed inputs."""
    lock_books(workspace, actor)
    invoice = IssuedInvoice.objects.filter(
        workspace=workspace, pk=invoice_id, kind=InvoiceDraft.Kind.PURCHASE, journal__sealed=True,
    ).select_related("draft").first()
    if not invoice:
        raise ValidationError("Choose a posted supplier invoice in this workspace.")
    if eligibility_reviewed is not True or not isinstance(evidence_reference, str) or not 1 <= len(evidence_reference.strip()) <= 200:
        raise ValidationError("Confirm supplier eligibility and record the review evidence.")
    if type(accepted_on) is not date or not invoice.draft.supply_on <= accepted_on <= timezone.localdate():
        raise ValidationError("Enter a confirmed acceptance date on or after receipt.")
    if written_due_on is not None and (type(written_due_on) is not date or written_due_on < accepted_on):
        raise ValidationError("The written due date cannot precede acceptance.")
    # Section 15 requires payment before the appointed day in the absence of written terms.
    deadline = (accepted_on + timedelta(days=15) if written_due_on is None
                else min(written_due_on, accepted_on + timedelta(days=45)))
    evidence_reference = evidence_reference.strip()
    previous = MsePaymentDeadline.objects.filter(invoice=invoice).first()
    if previous:
        if (previous.accepted_on, previous.written_due_on, previous.evidence_reference) != (
            accepted_on, written_due_on, evidence_reference,
        ):
            raise ValidationError("The MSE deadline review is already recorded for this invoice.")
        return previous
    return MsePaymentDeadline.objects.create(
        invoice=invoice, accepted_on=accepted_on, written_due_on=written_due_on, deadline=deadline,
        evidence_reference=evidence_reference, recorded_by=actor,
    )
