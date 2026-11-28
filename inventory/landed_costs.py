from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounting.models import AccountGroup, Journal, JournalLine
from accounting.services import lock_books, post_journal

from .costing import CostMethod, allocate_landed_cost, validate_decimal
from .models import LandedCharge, LandedChargeAllocation, PurchaseCost, StockMovement, ValuationEvent, ValuationLayer


MAX_LANDED_RECEIPTS = 20
SOURCE_KINDS = (Journal.Kind.GENERAL, Journal.Kind.ADJUSTMENT, Journal.Kind.PAYMENT)


def eligible_expense_lines(workspace):
    return JournalLine.objects.filter(
        journal__workspace=workspace, journal__sealed=True, journal__reversal__isnull=True,
        journal__kind__in=SOURCE_KINDS, side=JournalLine.Side.DEBIT, ledger__workspace=workspace,
        ledger__group__workspace=workspace, ledger__group__kind=AccountGroup.Kind.EXPENSE,
    ).select_related("journal", "ledger__group")


def _allocation_anchor(workspace, purchase, posted_on):
    movement = purchase.receipt.movement
    pool = StockMovement.objects.filter(workspace=workspace, lot__product_id=movement.lot.product_id,
                                        lot__unit=movement.lot.unit)
    anchor = ValuationEvent.objects.filter(movement__in=pool).order_by("-movement__posted_on", "-movement_id").first()
    if anchor.movement.posted_on > posted_on or pool.filter(posted_on__lte=posted_on, valuation__isnull=True).exists():
        raise ValidationError("Use the current valuation date and review any unvalued movements before allocating charges.")
    if anchor.landed_allocations.filter(charge__journal__date__gt=posted_on).exists():
        raise ValidationError("The charge date cannot precede a saved charge for this cost pool.")
    if purchase.receipt.method == CostMethod.FIFO:
        layer = ValuationLayer.objects.select_for_update().get(receipt=purchase.receipt)
        if layer.quantity != movement.quantity:
            raise ValidationError("Review the cost variance for receipts already consumed before allocating late charges.")
        return anchor, layer

    after_receipt = Q(posted_on__gt=movement.posted_on) | Q(posted_on=movement.posted_on, pk__gt=movement.pk)
    if pool.filter(after_receipt, kind=StockMovement.Kind.ISSUE, posted_on__lte=posted_on).exists():
        raise ValidationError("Review the weighted-average pool after a stock issue before allocating late charges.")
    return anchor, None


@transaction.atomic
def allocate_purchase_charge(workspace, actor, *, source_line_id, purchase_ids, kind, posted_on):
    if not settings.INTERNAL_STOCK_ACCOUNTING:
        raise PermissionDenied("Internal stock accounting is disabled.")
    lock_books(workspace, actor)
    purchase_ids = tuple(purchase_ids)
    if not 1 <= len(purchase_ids) <= MAX_LANDED_RECEIPTS or len(set(purchase_ids)) != len(purchase_ids):
        raise ValidationError(f"Choose up to {MAX_LANDED_RECEIPTS} distinct capitalised receipts.")
    if kind not in LandedCharge.Kind.values or type(posted_on) is not date or posted_on > timezone.localdate():
        raise ValidationError("Choose a landed charge type and a date on or before today.")
    source = eligible_expense_lines(workspace).filter(pk=source_line_id).first()
    if source is None or source.journal.date > posted_on:
        raise ValidationError("Choose a sealed freight or packaging expense line on or before the allocation date.")
    previous = LandedCharge.objects.filter(workspace=workspace, source_line=source).select_related("journal").first()
    if previous:
        if (previous.kind, previous.journal.date, set(previous.allocations.values_list("purchase_id", flat=True))) != (
            kind, posted_on, set(purchase_ids),
        ):
            raise ValidationError("This expense line was already allocated with different details.")
        return previous

    purchases = list(PurchaseCost.objects.filter(
        pk__in=purchase_ids, invoice__workspace=workspace, invoice__posting_on__lte=posted_on,
        invoice__cancellation__isnull=True, invoice__returns__isnull=True, receipt__movement__workspace=workspace,
        inventory_ledger__workspace=workspace, inventory_ledger__group__workspace=workspace,
        inventory_ledger__group__kind=AccountGroup.Kind.ASSET,
    ).select_related("inventory_ledger__group", "receipt__movement__lot").order_by("pk"))
    assets = {purchase.inventory_ledger_id for purchase in purchases}
    if len(purchases) != len(purchase_ids) or len(assets) != 1:
        raise ValidationError("Choose active purchases in this company that use the same inventory asset ledger.")
    amounts = allocate_landed_cost(source.amount, (purchase.receipt.amount for purchase in purchases))
    anchors = [_allocation_anchor(workspace, purchase, posted_on) for purchase in purchases]
    added = defaultdict(Decimal)
    for (anchor, _), amount in zip(anchors, amounts):
        added[anchor] += amount
    for anchor, amount in added.items():
        prior_total = sum(anchor.landed_allocations.values_list("amount", flat=True), Decimal(0))
        validate_decimal(anchor.closing_amount + prior_total + amount, digits=18, places=2, label="stock value")

    journal = post_journal(
        workspace, actor, date=posted_on, kind=Journal.Kind.STOCK_LANDED, reference=f"LC-{source.pk}",
        narration=f"Capitalise reviewed {kind} for purchased stock",
        submission_key=uuid5(NAMESPACE_URL, f"steel-quotes/purchase-charge/{source.pk}"),
        lines=[(purchases[0].inventory_ledger, "D", source.amount), (source.ledger, "C", source.amount)],
        stock_workflow=True,
    )
    charge = LandedCharge.objects.create(workspace=workspace, source_line=source, journal=journal,
                                         kind=kind, recorded_by=actor)
    for purchase, (anchor, layer), amount in zip(purchases, anchors, amounts):
        if layer is not None:
            layer.amount += amount
            validate_decimal(layer.amount, digits=15, places=2, label="landed FIFO layer value")
            layer.save(update_fields=["amount"])
        LandedChargeAllocation.objects.create(charge=charge, purchase=purchase, anchor=anchor, amount=amount)
    return charge
