from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from django.core.exceptions import ValidationError
from django.core.validators import DecimalValidator
from django.db import transaction

from accounting.services import lock_books
from dashboard.models import Product

from .models import StockCount, StockLot, StockMovement, StockPosition, StorageLocation
from .stock import check_lot_chronology, record_stock_movement, validate_stock_metadata


@transaction.atomic
def record_physical_count(workspace, actor, *, lot_id, location_id, counted, posted_on, reference, submission_key):
    lock_books(workspace, actor)
    lot = StockLot.objects.filter(workspace=workspace, product__owner_id=workspace.owner_id, pk=lot_id).first()
    location = StorageLocation.objects.filter(warehouse__workspace=workspace, pk=location_id).first()
    if lot is None or location is None:
        raise ValidationError("Choose a lot and storage location in this company.")
    if not isinstance(counted, Decimal) or not counted.is_finite() or counted < 0:
        raise ValidationError("Enter a count of zero or more.")
    DecimalValidator(14, 3)(counted)
    if lot.unit == Product.Unit.PIECE and counted != counted.to_integral_value():
        raise ValidationError("Enter a whole number of pieces.")
    reference = validate_stock_metadata(posted_on, reference, submission_key)

    previous = StockCount.objects.filter(workspace=workspace, submission_key=submission_key).select_related("position").first()
    if previous:
        recorded = (previous.position.lot_id, previous.position.location_id, previous.counted,
                    previous.posted_on, previous.reference)
        if recorded != (lot_id, location_id, counted, posted_on, reference):
            raise ValidationError("This submission key already belongs to a different physical count.")
        return previous
    check_lot_chronology(lot, posted_on)
    position, _ = StockPosition.objects.get_or_create(lot=lot, location=location)
    if counted < position.reserved:
        raise ValidationError("Resolve the reservation before recording a count below reserved stock.")
    before = position.on_hand
    difference = counted - before
    movement = None
    if difference:
        route = {"destination_id": location.pk} if difference > 0 else {"source_id": location.pk}
        movement = record_stock_movement(
            workspace, actor, lot_id=lot.pk,
            kind=StockMovement.Kind.RECEIPT if difference > 0 else StockMovement.Kind.ISSUE,
            quantity=abs(difference), posted_on=posted_on, reference=reference,
            submission_key=uuid5(NAMESPACE_URL, f"inventory-physical-count:{workspace.pk}:{submission_key}"), **route,
        )
    return StockCount.objects.create(
        workspace=workspace, position=position, before=before, counted=counted, adjustment=movement,
        posted_on=posted_on, reference=reference, submission_key=submission_key, recorded_by=actor,
    )
