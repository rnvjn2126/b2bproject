from datetime import date
from uuid import NAMESPACE_URL, uuid5

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounting.models import Journal, Period
from accounting.services import lock_books, post_journal

from .models import InvoiceDraft, IssuedInvoice
from .posting import plan_invoice_posting, resolve_invoice_lines
from .services import eligible_movements
from .tax import check_decimal


@transaction.atomic
def issue_internal_sale(workspace, actor, *, draft_id, posting_on, confirmed_total, ledger_ids):
    """Issue a synthetic internal sales record with its sealed journal in one transaction."""
    if not settings.INTERNAL_INVOICE_ISSUANCE:
        raise PermissionDenied("Internal invoice issuance is disabled.")
    lock_books(workspace, actor)
    draft = InvoiceDraft.objects.filter(workspace=workspace, pk=draft_id, kind=InvoiceDraft.Kind.SALES).first()
    if draft is None:
        raise ValidationError("Choose a sales draft in this workspace.")
    check_decimal(confirmed_total, 15, 2)
    if type(posting_on) is not date or posting_on != draft.supply_on:
        raise ValidationError("For internal issuance, use the confirmed dispatch date.")
    if confirmed_total != draft.total:
        raise ValidationError("The confirmed total must match the saved draft.")

    existing = IssuedInvoice.objects.filter(workspace=workspace, draft=draft).first()
    if existing:
        if existing.posting_on != posting_on or existing.total != confirmed_total or existing.ledger_ids != ledger_ids:
            raise ValidationError("This draft was already issued with different inputs.")
        return existing
    if (draft.registration.workspace_id != workspace.pk or draft.rate.workspace_id != workspace.pk
            or not eligible_movements(workspace).filter(pk=draft.movement_id, sales_line__isnull=False,
                                                        date=posting_on).exists()):
        raise ValidationError("The dispatch or tax inputs are unavailable in this workspace.")
    period = Period.objects.filter(year__workspace=workspace, starts_on__lte=posting_on, ends_before__gt=posting_on,
                                   locked_at__isnull=True).select_related("year").first()
    if period is None:
        raise ValidationError("The accounting date needs an open period.")
    if set(ledger_ids) != {role for role, _, _ in plan_invoice_posting(draft)}:
        raise ValidationError("Choose exactly the ledgers required by this invoice.")
    lines = resolve_invoice_lines(workspace, draft, ledger_ids)
    last = IssuedInvoice.objects.filter(workspace=workspace, year=period.year).order_by("-sequence").values_list(
        "sequence", flat=True,
    ).first()
    sequence = (last or 0) + 1
    number = IssuedInvoice.number_for(period.year.start_year, sequence)
    journal = post_journal(
        workspace, actor, date=posting_on, kind=Journal.Kind.SALES_INVOICE, reference=number,
        narration="Internal sales invoice", submission_key=uuid5(NAMESPACE_URL, f"steel-quotes/internal-invoice/{draft.pk}"),
        lines=lines,
    )
    return IssuedInvoice.objects.create(
        workspace=workspace, draft=draft, year=period.year, sequence=sequence, number=number, posting_on=posting_on,
        journal=journal, total=draft.total, snapshot=draft.snapshot, ledger_ids=ledger_ids, issued_by=actor,
    )
