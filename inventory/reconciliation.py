from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounting.models import AccountGroup, JournalLine, Ledger
from dashboard.models import BusinessAccount

from .models import StockMovement


@dataclass
class ReconciliationPool:
    product: str
    unit: str
    on_hand: Decimal = Decimal(0)
    valued_quantity: Decimal = Decimal(0)
    inventory_value: Decimal = Decimal("0.00")
    unvalued_movements: int = 0

    @property
    def quantity_gap(self):
        return self.on_hand - self.valued_quantity


@dataclass(frozen=True)
class StockReconciliation:
    as_of: date
    ledger: Ledger
    pools: tuple[ReconciliationPool, ...]
    ledger_balance: Decimal

    @property
    def inventory_value(self):
        return sum((pool.inventory_value for pool in self.pools), Decimal("0.00"))

    @property
    def difference(self):
        return self.inventory_value - self.ledger_balance

    @property
    def unvalued_movements(self):
        return sum(pool.unvalued_movements for pool in self.pools)

    @property
    def reconciled(self):
        return self.difference == 0 and not any(pool.unvalued_movements or pool.quantity_gap for pool in self.pools)


def stock_asset_ledgers(workspace):
    return Ledger.objects.filter(workspace=workspace, group__workspace=workspace, group__kind=AccountGroup.Kind.ASSET)


@transaction.atomic
def reconcile_stock_to_ledger(workspace, actor, *, ledger_id, as_of):
    """Compare dated stock valuations with the selected sealed asset ledger."""
    if workspace.owner_id != actor.pk or not actor.is_active:
        raise PermissionDenied
    if type(as_of) is not date or as_of > timezone.localdate():
        raise ValidationError("Choose an as-of date on or before today.")
    # Hold the same workspace lock as posting on databases that support row locking.
    BusinessAccount.objects.select_for_update().only("pk").get(pk=workspace.pk, owner=actor)
    ledger = stock_asset_ledgers(workspace).filter(pk=ledger_id).first()
    if ledger is None:
        raise ValidationError("Choose an asset ledger from your company.")
    movements = StockMovement.objects.filter(
        workspace=workspace, lot__workspace=workspace, lot__product__owner_id=workspace.owner_id, posted_on__lte=as_of,
    ).order_by("posted_on", "pk").values_list(
        "lot__product_id", "lot__product__name", "lot__unit", "kind", "quantity",
        "valuation__closing_quantity", "valuation__closing_amount",
    )
    pools = {}
    for product_id, product, unit, kind, quantity, valued_quantity, amount in movements.iterator():
        key = product_id, unit
        if key not in pools:
            pools[key] = ReconciliationPool(product, unit)
        pool = pools[key]
        if kind == StockMovement.Kind.RECEIPT:
            pool.on_hand += quantity
        elif kind == StockMovement.Kind.ISSUE:
            pool.on_hand -= quantity
        if valued_quantity is None:
            pool.unvalued_movements += 1
        else:
            pool.valued_quantity, pool.inventory_value = valued_quantity, amount

    lines = JournalLine.objects.filter(
        ledger=ledger, journal__workspace=workspace, journal__sealed=True, journal__date__lte=as_of,
    ).order_by().values_list("side", "amount")
    # Sum Decimal rows exactly on SQLite as well as PostgreSQL.
    ledger_balance = sum((amount if side == JournalLine.Side.DEBIT else -amount
                          for side, amount in lines.iterator()), Decimal("0.00"))
    return StockReconciliation(
        as_of, ledger, tuple(sorted(pools.values(), key=lambda pool: (pool.product, pool.unit))), ledger_balance,
    )
