from uuid import NAMESPACE_URL, uuid5

from django.core.exceptions import ValidationError
from django.db import transaction

from accounting.services import lock_books

from .models import ReservationAction, StockMovement, StockPosition, StockReservation
from .stock import check_lot_chronology, record_stock_movement, validate_stock_input


@transaction.atomic
def reserve_stock(workspace, actor, *, position_id, quantity, posted_on, reference, submission_key):
    lock_books(workspace, actor)
    position = StockPosition.objects.filter(
        pk=position_id, lot__workspace=workspace, lot__product__owner_id=workspace.owner_id,
        location__warehouse__workspace=workspace,
    ).select_related("lot").first()
    if position is None:
        raise ValidationError("Choose a stock position in this company.")
    reference = validate_stock_input(position.lot, quantity, posted_on, reference, submission_key)
    previous = StockReservation.objects.filter(workspace=workspace, submission_key=submission_key).first()
    if previous:
        if (previous.position_id, previous.quantity, previous.posted_on, previous.reference) != (
            position_id, quantity, posted_on, reference,
        ):
            raise ValidationError("This submission key already belongs to a different reservation.")
        return previous
    check_lot_chronology(position.lot, posted_on)
    if position.available < quantity:
        raise ValidationError("The reservation would exceed available stock.")
    position.reserved += quantity
    position.save(update_fields=["reserved"])
    return StockReservation.objects.create(
        workspace=workspace, position=position, quantity=quantity, remaining=quantity, posted_on=posted_on,
        reference=reference, submission_key=submission_key, recorded_by=actor,
    )


@transaction.atomic
def record_reservation_action(workspace, actor, *, reservation_id, kind, quantity, posted_on, reference,
                              submission_key, actual_kg=None, order_movement_id=None):
    lock_books(workspace, actor)
    reservation = StockReservation.objects.filter(
        pk=reservation_id, workspace=workspace, position__lot__workspace=workspace,
        position__lot__product__owner_id=workspace.owner_id,
        position__location__warehouse__workspace=workspace,
    ).select_related("position__lot").first()
    if reservation is None:
        raise ValidationError("Choose a reservation in this company.")
    position = reservation.position
    reference = validate_stock_input(position.lot, quantity, posted_on, reference, submission_key)
    if kind not in ReservationAction.Kind.values:
        raise ValidationError("Choose a reservation action.")
    if kind == ReservationAction.Kind.RELEASE and (actual_kg is not None or order_movement_id is not None):
        raise ValidationError("Add weight or an order movement only when issuing reserved stock.")
    previous = reservation.actions.filter(submission_key=submission_key).select_related("movement").first()
    if previous:
        old_movement = previous.movement
        recorded = (previous.kind, previous.quantity, previous.posted_on, previous.reference,
                    old_movement.actual_kg if old_movement else None,
                    old_movement.order_movement_id if old_movement else None)
        if recorded != (kind, quantity, posted_on, reference, actual_kg, order_movement_id):
            raise ValidationError("This submission key already belongs to a different reservation action.")
        return previous

    check_lot_chronology(position.lot, posted_on)
    if quantity > reservation.remaining:
        raise ValidationError("This action would exceed the remaining reservation.")
    position.reserved -= quantity
    position.save(update_fields=["reserved"])
    reservation.remaining -= quantity
    reservation.save(update_fields=["remaining"])
    movement = None
    if kind == ReservationAction.Kind.ISSUE:
        movement = record_stock_movement(
            workspace, actor, lot_id=position.lot_id, source_id=position.location_id, kind=StockMovement.Kind.ISSUE,
            quantity=quantity, posted_on=posted_on, reference=reference,
            submission_key=uuid5(NAMESPACE_URL, f"inventory-reservation:{reservation.pk}:{submission_key}"),
            actual_kg=actual_kg, order_movement_id=order_movement_id,
        )
    return ReservationAction.objects.create(
        reservation=reservation, movement=movement, kind=kind, quantity=quantity, posted_on=posted_on,
        reference=reference, submission_key=submission_key, recorded_by=actor,
    )
