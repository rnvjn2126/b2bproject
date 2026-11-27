from collections import defaultdict
from datetime import date
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import DecimalValidator
from django.db import transaction
from django.db.models import Min, Q
from django.utils import timezone

from accounting.services import lock_books
from dashboard.models import Product

from .models import ReorderPolicy, StockMovement, StockPosition, Warehouse


def company_positions(workspace):
    return StockPosition.objects.filter(
        lot__workspace=workspace, lot__product__owner_id=workspace.owner_id, location__warehouse__workspace=workspace,
    ).select_related("lot__product", "location__warehouse").order_by("location__warehouse__code", "location__code", "lot__code")


@transaction.atomic
def set_reorder_policy(workspace, actor, *, product_id, warehouse_id, minimum_available):
    lock_books(workspace, actor)
    product = Product.objects.filter(owner_id=workspace.owner_id, pk=product_id).first()
    warehouse = Warehouse.objects.filter(workspace=workspace, pk=warehouse_id).first()
    if product is None or warehouse is None:
        raise ValidationError("Choose a catalogue product and a warehouse in this company.")
    if not isinstance(minimum_available, Decimal) or not minimum_available.is_finite() or minimum_available < 0:
        raise ValidationError("Enter a reorder threshold of zero or more.")
    DecimalValidator(14, 3)(minimum_available)
    if product.unit == Product.Unit.PIECE and minimum_available != minimum_available.to_integral_value():
        raise ValidationError("Enter a whole number of pieces for the reorder threshold.")
    policy, _ = ReorderPolicy.objects.update_or_create(
        workspace=workspace, product=product, warehouse=warehouse,
        defaults={"minimum_available": minimum_available, "unit": product.unit},
    )
    return policy


@dataclass(frozen=True)
class ReorderStatus:
    policy: ReorderPolicy
    available: Decimal
    mixed_units: bool

    @property
    def needs_reorder(self):
        return not self.mixed_units and self.available <= self.policy.minimum_available


def reorder_status(workspace):
    by_product_and_warehouse = defaultdict(lambda: defaultdict(Decimal))
    for position in company_positions(workspace).filter(on_hand__gt=0):
        group = by_product_and_warehouse[position.lot.product_id, position.location.warehouse_id]
        group[position.lot.unit] += position.available
    policies = ReorderPolicy.objects.filter(
        workspace=workspace, product__owner_id=workspace.owner_id, warehouse__workspace=workspace,
    ).select_related("product", "warehouse").order_by("warehouse__code", "product__name")
    results = []
    for policy in policies:
        amounts = by_product_and_warehouse[policy.product_id, policy.warehouse_id]
        mixed = any(unit != policy.unit for unit in amounts) or policy.product.unit != policy.unit
        results.append(ReorderStatus(policy, amounts[policy.unit], mixed))
    return results


@dataclass(frozen=True)
class StockAge:
    position: StockPosition
    first_receipt: date | None
    age_days: int | None


def stock_ageing(workspace):
    today = timezone.localdate()
    positions = company_positions(workspace).filter(on_hand__gt=0).annotate(
        first_receipt=Min("lot__movements__posted_on", filter=Q(
            lot__movements__kind=StockMovement.Kind.RECEIPT, lot__movements__physical_count__isnull=True,
        )),
    )
    return [StockAge(row, row.first_receipt, (today - row.first_receipt).days if row.first_receipt else None)
            for row in positions]
