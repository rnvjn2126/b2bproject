from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext
from uuid import UUID

from django.core.exceptions import ValidationError
from django.core.validators import DecimalValidator
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounting.services import lock_books
from dashboard.models import Product
from orders.models import OrderMovement, SalesOrder
from orders.services import check_quantity

from .geometry import KG_PER_TONNE, MM_PER_M
from .models import ReservationAction, StockCount, StockLot, StockMovement, StockPosition, StockReservation, StorageLocation


def _check_order_movement(workspace, lot, kind, order_movement_id, posted_on, quantity):
    approved = SalesOrder.Status.APPROVED
    common = {"pk": order_movement_id, "date": posted_on, "quantity": quantity}
    if kind == StockMovement.Kind.RECEIPT:
        relation = "purchase_order__requirement__"
        common["purchase_order__status"] = approved
    elif kind == StockMovement.Kind.ISSUE:
        relation = "sales_line__"
    else:
        raise ValidationError("Link only a receipt or issue to an order movement.")
    scope = {
        f"{relation}order__workspace": workspace, f"{relation}order__status": approved,
        f"{relation}quote_line__rfq_line__product_id": lot.product_id, f"{relation}unit": lot.unit,
    }
    if not OrderMovement.objects.filter(**common, **scope).exists():
        raise ValidationError("Choose an approved order movement with the same company, product, quantity, date and unit.")
    if StockMovement.objects.filter(order_movement_id=order_movement_id).exists():
        raise ValidationError("This order movement has already been recorded in stock.")


def _theoretical_mass(lot, quantity):
    if lot.nominal_kg_per_m is None:
        return None
    if lot.unit == Product.Unit.METRE:
        metres = quantity
    elif lot.unit == Product.Unit.PIECE and lot.length_mm is not None:
        metres = quantity * lot.length_mm / MM_PER_M
    else:
        return None
    with localcontext() as context:
        context.prec = 40
        weight = (metres * lot.nominal_kg_per_m).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    DecimalValidator(18, 6)(weight)
    return weight


def validate_stock_input(lot, quantity, posted_on, reference, submission_key):
    check_quantity(quantity)
    if lot.unit == Product.Unit.PIECE and quantity != quantity.to_integral_value():
        raise ValidationError("Enter a whole number of pieces.")
    return validate_stock_metadata(posted_on, reference, submission_key)


def validate_stock_metadata(posted_on, reference, submission_key):
    if type(posted_on) is not date or posted_on > timezone.localdate() or not isinstance(submission_key, UUID):
        raise ValidationError("Choose a posting date on or before today and a valid submission key.")
    if not isinstance(reference, str) or not 1 <= len(reference.strip()) <= 100:
        raise ValidationError("Enter a stock movement reference up to 100 characters.")
    return reference.strip()


def check_lot_chronology(lot, posted_on):
    if (lot.movements.filter(posted_on__gt=posted_on).exists()
            or StockReservation.objects.filter(position__lot=lot, posted_on__gt=posted_on).exists()
            or StockCount.objects.filter(position__lot=lot, posted_on__gt=posted_on).exists()
            or ReservationAction.objects.filter(reservation__position__lot=lot, posted_on__gt=posted_on).exists()):
        raise ValidationError("Post stock activity in chronological order for this lot.")


@transaction.atomic
def record_stock_movement(workspace, actor, *, lot_id, kind, source_id=None, destination_id=None, quantity,
                          posted_on, reference, submission_key, actual_kg=None, order_movement_id=None):
    """Update stock positions and append one movement in a single company-locked transaction."""
    lock_books(workspace, actor)
    lot = StockLot.objects.filter(workspace=workspace, product__owner_id=workspace.owner_id, pk=lot_id).first()
    if lot is None:
        raise ValidationError("Choose a lot in this company.")
    reference = validate_stock_input(lot, quantity, posted_on, reference, submission_key)
    if actual_kg is not None:
        if not isinstance(actual_kg, Decimal) or not actual_kg.is_finite() or actual_kg <= 0:
            raise ValidationError("Enter a positive measured weight in kilograms.")
        DecimalValidator(18, 6)(actual_kg)
        expected_kg = {Product.Unit.KG: quantity, Product.Unit.TONNE: quantity * KG_PER_TONNE}.get(lot.unit)
        if expected_kg is not None and actual_kg != expected_kg:
            raise ValidationError("Measured kilograms must agree with the movement quantity for mass-based stock.")

    routes = {StockMovement.Kind.RECEIPT: (False, True), StockMovement.Kind.ISSUE: (True, False),
              StockMovement.Kind.TRANSFER: (True, True)}
    if routes.get(kind) != (source_id is not None, destination_id is not None) or source_id == destination_id:
        raise ValidationError("Choose the correct distinct locations for this movement.")
    location_ids = {pk for pk in (source_id, destination_id) if pk is not None}
    if StorageLocation.objects.filter(warehouse__workspace=workspace, pk__in=location_ids).count() != len(location_ids):
        raise ValidationError("Choose stock locations in this company.")

    previous = StockMovement.objects.filter(workspace=workspace, submission_key=submission_key).first()
    if previous:
        prior = (previous.lot_id, previous.kind, previous.source_id, previous.destination_id, previous.quantity,
                 previous.posted_on, previous.reference, previous.actual_kg, previous.order_movement_id)
        if prior != (lot.pk, kind, source_id, destination_id, quantity, posted_on, reference, actual_kg, order_movement_id):
            raise ValidationError("This submission key already belongs to a different stock movement.")
        return previous

    check_lot_chronology(lot, posted_on)
    if StockMovement.objects.filter(
        workspace=workspace, lot__product_id=lot.product_id, lot__unit=lot.unit,
    ).filter(
        Q(posted_on__gt=posted_on, valuation__isnull=False)
        | Q(valuation__landed_allocations__charge__journal__date__gt=posted_on),
    ).exists():
        raise ValidationError("This date precedes an existing valuation or landed charge for this product and unit.")
    if order_movement_id is not None:
        _check_order_movement(workspace, lot, kind, order_movement_id, posted_on, quantity)

    if source_id is not None:
        source = StockPosition.objects.filter(lot=lot, location_id=source_id).first()
        if source is None or source.available < quantity:
            raise ValidationError("The movement would exceed available stock.")
        source.on_hand -= quantity
        source.save(update_fields=["on_hand"])
    if destination_id is not None:
        destination, _ = StockPosition.objects.get_or_create(lot=lot, location_id=destination_id)
        destination.on_hand += quantity
        DecimalValidator(14, 3)(destination.on_hand)
        destination.save(update_fields=["on_hand"])

    return StockMovement.objects.create(
        workspace=workspace, lot=lot, kind=kind, source_id=source_id, destination_id=destination_id,
        order_movement_id=order_movement_id, quantity=quantity, actual_kg=actual_kg,
        theoretical_kg=_theoretical_mass(lot, quantity), posted_on=posted_on, reference=reference,
        submission_key=submission_key, recorded_by=actor,
    )


def unvalued_stock_correction(workspace, *, movement_id, original, kind, posted_on, quantity):
    return StockMovement.objects.filter(
        pk=movement_id, workspace=workspace, lot=original.lot, kind=kind, posted_on=posted_on, quantity=quantity,
        order_movement__isnull=True, physical_count__isnull=True, valuation__isnull=True,
    ).first()
