import re
from datetime import date
from uuid import NAMESPACE_URL, uuid5

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounting.models import Journal, Period
from accounting.services import lock_books, post_journal

from .models import InvoiceCancellation, InvoiceDraft, IssuedInvoice
from .posting import plan_invoice_posting, resolve_invoice_lines
from .services import eligible_movements
from .tax import check_decimal, validate_gstin


def issue_internal_sale(workspace, actor, *, draft_id, posting_on, confirmed_total, ledger_ids):
    return _issue_internal(workspace, actor, kind=InvoiceDraft.Kind.SALES, draft_id=draft_id,
                           posting_on=posting_on, confirmed_total=confirmed_total, ledger_ids=ledger_ids)


def issue_internal_purchase(workspace, actor, *, draft_id, posting_on, confirmed_total, ledger_ids,
                            supplier_invoice_date, supplier_reference, recoverable_input_tax):
    return _issue_internal(
        workspace, actor, kind=InvoiceDraft.Kind.PURCHASE, draft_id=draft_id, posting_on=posting_on,
        confirmed_total=confirmed_total, ledger_ids=ledger_ids, supplier_invoice_date=supplier_invoice_date,
        supplier_reference=supplier_reference, recoverable_input_tax=recoverable_input_tax,
    )


@transaction.atomic
def _issue_internal(workspace, actor, *, kind, draft_id, posting_on, confirmed_total, ledger_ids,
                    supplier_invoice_date=None, supplier_reference="", recoverable_input_tax=None):
    """Store an internal invoice record and its sealed journal in one transaction."""
    if not settings.INTERNAL_INVOICE_ISSUANCE:
        raise PermissionDenied("Internal invoice issuance is disabled.")
    lock_books(workspace, actor)
    draft = InvoiceDraft.objects.filter(workspace=workspace, pk=draft_id, kind=kind).first()
    if draft is None:
        raise ValidationError("Choose an invoice draft of this type in your workspace.")
    check_decimal(confirmed_total, 15, 2)
    if confirmed_total != draft.total:
        raise ValidationError("The confirmed total must match the saved draft.")
    sales = kind == InvoiceDraft.Kind.SALES
    if type(posting_on) is not date or posting_on < draft.supply_on or (sales and posting_on != draft.supply_on):
        raise ValidationError("For internal issuance, use the dispatch date or a date on or after the receipt.")
    supplier_document = {}
    if not sales:
        if (type(supplier_invoice_date) is not date or supplier_invoice_date > posting_on
                or supplier_invoice_date.isoformat() != draft.snapshot.get("supplier_invoice_date")):
            raise ValidationError("Use the supplier invoice date recorded with the actual purchase draft.")
        if not isinstance(supplier_reference, str) or not re.fullmatch(r"[A-Za-z0-9/-]{1,16}", supplier_reference.strip()):
            raise ValidationError("Enter the supplier invoice reference.")
        supplier_reference = supplier_reference.strip().upper()
        if not isinstance(recoverable_input_tax, bool):
            raise ValidationError("Explicitly confirm the purchase input tax treatment.")
        supplier_gstin = draft.snapshot["party"]["gstin"]
        validate_gstin(supplier_gstin)
        supplier_document = {
            "supplier_invoice_date": supplier_invoice_date, "supplier_reference": supplier_reference,
            "supplier_gstin": supplier_gstin, "supplier_year": supplier_invoice_date.year - (supplier_invoice_date.month < 4),
            "recoverable_input_tax": recoverable_input_tax,
        }

    existing = IssuedInvoice.objects.filter(workspace=workspace, draft=draft).first()
    if existing:
        if (existing.posting_on != posting_on or existing.total != confirmed_total or existing.ledger_ids != ledger_ids
                or any(getattr(existing, field) != value for field, value in supplier_document.items())):
            raise ValidationError("This draft was already issued with different inputs.")
        return existing
    if supplier_document and IssuedInvoice.objects.filter(
        workspace=workspace, kind=kind, supplier_gstin=supplier_document["supplier_gstin"],
        supplier_year=supplier_document["supplier_year"], supplier_reference=supplier_reference,
    ).exists():
        raise ValidationError("This supplier document is already recorded in this workspace.")
    if (draft.registration.workspace_id != workspace.pk or draft.rate.workspace_id != workspace.pk
            or not eligible_movements(workspace).filter(pk=draft.movement_id, sales_line__isnull=not sales,
                                                        date=draft.supply_on).exists()):
        raise ValidationError("The confirmed movement or tax inputs are unavailable in this workspace.")
    period = Period.objects.filter(year__workspace=workspace, starts_on__lte=posting_on, ends_before__gt=posting_on,
                                   locked_at__isnull=True).select_related("year").first()
    if period is None:
        raise ValidationError("The accounting date needs an open period.")
    plan = plan_invoice_posting(draft, recoverable_input_tax=recoverable_input_tax)
    if set(ledger_ids) != {role for role, _, _ in plan}:
        raise ValidationError("Choose exactly the ledgers required by this invoice.")
    lines = resolve_invoice_lines(workspace, draft, ledger_ids, recoverable_input_tax=recoverable_input_tax)
    last = IssuedInvoice.objects.filter(workspace=workspace, year=period.year).order_by("-sequence").values_list(
        "sequence", flat=True,
    ).first()
    sequence = (last or 0) + 1
    number = IssuedInvoice.number_for(kind, period.year.start_year, sequence)
    journal_kind = Journal.Kind.SALES_INVOICE if sales else Journal.Kind.PURCHASE_INVOICE
    journal = post_journal(
        workspace, actor, date=posting_on, kind=journal_kind, reference=number, narration=journal_kind.label,
        submission_key=uuid5(NAMESPACE_URL, f"steel-quotes/internal-invoice/{draft.pk}"), lines=lines,
    )
    return IssuedInvoice.objects.create(
        workspace=workspace, draft=draft, year=period.year, sequence=sequence, number=number,
        kind=kind, posting_on=posting_on, journal=journal, total=draft.total, snapshot=draft.snapshot,
        ledger_ids=ledger_ids, issued_by=actor, **supplier_document,
    )


@transaction.atomic
def cancel_internal_invoice(workspace, actor, *, invoice_id, posting_on, reason):
    """Reverse an internal invoice while retaining the issued document and its reference."""
    if not settings.INTERNAL_INVOICE_ISSUANCE:
        raise PermissionDenied("Internal invoice issuance is disabled.")
    lock_books(workspace, actor)
    invoice = IssuedInvoice.objects.filter(workspace=workspace, pk=invoice_id).select_related("journal").first()
    if invoice is None:
        raise ValidationError("Choose an issued invoice in your workspace.")
    if type(posting_on) is not date or posting_on < invoice.posting_on:
        raise ValidationError("The correction date cannot precede the original posting.")
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
        raise ValidationError("Enter a cancellation reason of up to 500 characters.")
    reason = reason.strip()
    existing = InvoiceCancellation.objects.filter(invoice=invoice).select_related("reversal").first()
    if existing:
        if existing.reason != reason or existing.reversal.date != posting_on:
            raise ValidationError("This invoice was already cancelled with different inputs.")
        return existing
    if invoice.returns.exists():
        raise ValidationError("An invoice with recorded returns cannot be fully cancelled.")

    reversal = post_journal(
        workspace, actor, date=posting_on, kind=Journal.Kind.REVERSAL, reference=f"VOID-{invoice.number}",
        narration=reason, submission_key=uuid5(NAMESPACE_URL, f"steel-quotes/internal-cancellation/{invoice.pk}"),
        reverses=invoice.journal, invoice_correction=True,
    )
    return InvoiceCancellation.objects.create(invoice=invoice, reversal=reversal, reason=reason, cancelled_by=actor)
