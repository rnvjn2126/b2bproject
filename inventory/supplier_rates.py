from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from accounting.services import lock_books
from dashboard.models import Product, Supplier
from orders.services import check_quantity

from .costing import PAISE, ZERO, validate_decimal
from .geometry import convert_quantity
from .models import SupplierDailyRate


MASS_UNITS = {Product.Unit.KG, Product.Unit.TONNE}


def company_daily_rates(workspace):
    return SupplierDailyRate.objects.filter(
        workspace=workspace, supplier__owner_id=workspace.owner_id, product__owner_id=workspace.owner_id,
    ).select_related("supplier", "product")


def compatible_units(source, target):
    return source == target or {source, target} <= MASS_UNITS


@transaction.atomic
def record_daily_rate(workspace, actor, *, supplier_id, product_id, unit, quoted_on, valid_through, unit_price,
                      available_quantity, freight, packaging, delivery_days, reference, submission_key):
    lock_books(workspace, actor)
    product = Product.objects.filter(owner_id=workspace.owner_id, pk=product_id).first()
    supplier = Supplier.objects.filter(owner_id=workspace.owner_id, pk=supplier_id).first()
    if product is None or supplier is None:
        raise ValidationError("Choose a product and supplier from your company.")
    if (type(quoted_on) is not date or type(valid_through) is not date
            or quoted_on > timezone.localdate() or valid_through < quoted_on):
        raise ValidationError("Use a quoted date on or before today and a valid-through date on or after it.")
    if type(delivery_days) is not int or not 0 <= delivery_days <= 365:
        raise ValidationError("Enter delivery lead time from 0 to 365 days.")
    if not isinstance(reference, str) or not 1 <= len(reference.strip()) <= 100 or not isinstance(submission_key, UUID):
        raise ValidationError("Enter a source reference up to 100 characters and a valid submission key.")
    validate_decimal(unit_price, digits=14, places=4, label="supplier unit price", positive=True)
    validate_decimal(available_quantity, digits=14, places=3, label="available supplier quantity")
    for amount in (freight, packaging):
        validate_decimal(amount, digits=15, places=2, label="supplier charge")
    if unit == Product.Unit.PIECE and available_quantity != available_quantity.to_integral_value():
        raise ValidationError("Enter a whole number of pieces.")
    fields = dict(supplier_id=supplier.pk, product_id=product.pk, unit=unit, quoted_on=quoted_on,
                  valid_through=valid_through, unit_price=unit_price, available_quantity=available_quantity,
                  freight=freight, packaging=packaging, delivery_days=delivery_days, reference=reference.strip())
    previous = company_daily_rates(workspace).filter(submission_key=submission_key).first()
    if previous:
        if any(getattr(previous, key) != value for key, value in fields.items()):
            raise ValidationError("This submission key already belongs to a different supplier rate.")
        return previous
    if unit not in Product.Unit.values or not compatible_units(unit, product.unit):
        raise ValidationError("Use the catalogue unit or an equivalent kilogram or tonne unit.")
    return SupplierDailyRate.objects.create(workspace=workspace, recorded_by=actor, submission_key=submission_key, **fields)


def latest_daily_rates(workspace, as_of, *, product_id=None):
    rows = company_daily_rates(workspace).filter(quoted_on__lte=as_of)
    if product_id is not None:
        rows = rows.filter(product_id=product_id)
    latest = rows.filter(product_id=OuterRef("product_id"), supplier_id=OuterRef("supplier_id")).values("pk")[:1]
    return rows.filter(pk=Subquery(latest))


@dataclass(frozen=True)
class ProcurementLine:
    rate: SupplierDailyRate
    quantity: Decimal
    material: Decimal
    landed: Decimal


@dataclass(frozen=True)
class ProcurementPlan:
    unit: str
    lines: tuple[ProcurementLine, ...]
    unfilled: Decimal

    @property
    def total(self):
        return sum((line.landed for line in self.lines), ZERO)

    @property
    def delivery_days(self):
        return max((line.rate.delivery_days for line in self.lines), default=None)


def recommend_procurement(workspace, *, product_id, quantity, as_of, max_delivery_days=None):
    product = Product.objects.filter(owner_id=workspace.owner_id, pk=product_id).first()
    if product is None or product.unit not in Product.Unit.values:
        raise ValidationError("Choose a catalogue product from your company.")
    if type(as_of) is not date or as_of > timezone.localdate():
        raise ValidationError("Choose a recommendation date on or before today.")
    if max_delivery_days is not None and (type(max_delivery_days) is not int or not 0 <= max_delivery_days <= 365):
        raise ValidationError("Enter maximum delivery lead time from 0 to 365 days.")
    check_quantity(quantity)
    if product.unit == Product.Unit.PIECE and quantity != quantity.to_integral_value():
        raise ValidationError("Enter a whole number of pieces.")
    rates = latest_daily_rates(workspace, as_of, product_id=product_id).filter(
        valid_through__gte=as_of, available_quantity__gt=0,
    )
    if max_delivery_days is not None:
        rates = rates.filter(delivery_days__lte=max_delivery_days)

    def proposal_line(rate, quantity, unit_price):
        material = (quantity * unit_price).quantize(PAISE, rounding=ROUND_HALF_UP)
        return ProcurementLine(rate, quantity, material, material + rate.freight + rate.packaging)

    precision = Decimal(1) if product.unit == Product.Unit.PIECE else Decimal("0.001")
    candidates = []
    for rate in rates:
        if compatible_units(rate.unit, product.unit):
            factor = convert_quantity(Decimal(1), rate.unit, product.unit)
            available = (rate.available_quantity * factor).quantize(precision, rounding=ROUND_FLOOR)
            if available:
                unit_price = rate.unit_price / factor
                sample = proposal_line(rate, min(available, quantity), unit_price)
                candidates.append((sample, unit_price))

    candidates.sort(key=lambda candidate: (
        candidate[0].landed / candidate[0].quantity, candidate[0].rate.delivery_days, candidate[0].rate.pk,
    ))
    left, split = quantity, []
    for sample, unit_price in candidates:
        chosen = min(left, sample.quantity)
        split.append(proposal_line(sample.rate, chosen, unit_price))
        left -= chosen
        if left == 0:
            break
    plans = [ProcurementPlan(product.unit, tuple(split), left)]
    # Charge a supplier's quoted fixed costs once when any quantity is selected.
    plans.extend(ProcurementPlan(product.unit, (sample,), ZERO) for sample, _ in candidates if sample.quantity == quantity)
    return min(plans, key=lambda plan: (plan.unfilled, plan.total, plan.delivery_days or 0, len(plan.lines)))
