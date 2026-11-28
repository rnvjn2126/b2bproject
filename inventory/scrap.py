from uuid import NAMESPACE_URL, UUID, uuid5

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounting.models import AccountGroup, Journal, Ledger
from accounting.services import lock_books, post_journal

from .costing import validate_decimal
from .models import ScrapDisposal, StockCutOutput, StockMovement
from .reconciliation import posted_asset_balance, stock_asset_ledgers
from .stock import record_stock_movement
from .valuation import value_stock_movement


@transaction.atomic
def dispose_scrap(workspace, actor, *, lot_id, source_id, quantity, actual_kg, posted_on, reference, submission_key,
                  inventory_ledger_id, loss_ledger_id):
    if not settings.INTERNAL_STOCK_ACCOUNTING:
        raise PermissionDenied("Internal stock accounting is disabled.")
    lock_books(workspace, actor)
    if not isinstance(submission_key, UUID):
        raise ValidationError("Enter a valid scrap disposal submission key.")
    if not StockCutOutput.objects.filter(
        cut__workspace=workspace, kind=StockCutOutput.Kind.SCRAP, receipt__movement__workspace=workspace,
        receipt__movement__lot_id=lot_id,
    ).exists():
        raise ValidationError("Choose a lot recorded as recoverable scrap in this company.")
    validate_decimal(actual_kg, digits=18, places=6, label="measured scrap weight", positive=True)
    asset = stock_asset_ledgers(workspace).filter(pk=inventory_ledger_id).select_related("group").first()
    loss = Ledger.objects.filter(
        pk=loss_ledger_id, workspace=workspace, group__workspace=workspace, group__kind=AccountGroup.Kind.EXPENSE,
    ).select_related("group").first()
    if asset is None or loss is None:
        raise ValidationError("Choose an inventory asset and a scrap loss expense ledger in this company.")

    move = record_stock_movement(
        workspace, actor, lot_id=lot_id, source_id=source_id, kind=StockMovement.Kind.ISSUE, quantity=quantity,
        actual_kg=actual_kg, posted_on=posted_on, reference=reference,
        submission_key=uuid5(NAMESPACE_URL, f"steel-quotes/scrap/{workspace.pk}/{submission_key}"),
    )
    event = value_stock_movement(workspace, actor, movement_id=move.pk)
    existing = ScrapDisposal.objects.filter(workspace=workspace, issue=event).first()
    if existing:
        if (existing.inventory_ledger_id, existing.loss_ledger_id) != (asset.pk, loss.pk):
            raise ValidationError("This scrap disposal already uses different ledgers.")
        return existing
    journal = None
    if event.amount:
        if posted_asset_balance(workspace, asset, posted_on) < event.amount:
            raise ValidationError("Review the inventory asset balance before posting a scrap loss.")
        journal = post_journal(
            workspace, actor, date=posted_on, kind=Journal.Kind.STOCK_SCRAP, reference=f"SCRAP-{move.pk}",
            narration=move.reference, submission_key=uuid5(NAMESPACE_URL, f"steel-quotes/scrap-loss/{move.pk}"),
            lines=[(loss, "D", event.amount), (asset, "C", event.amount)], stock_workflow=True,
        )
    return ScrapDisposal.objects.create(workspace=workspace, issue=event, inventory_ledger=asset,
                                        loss_ledger=loss, journal=journal, recorded_by=actor)
