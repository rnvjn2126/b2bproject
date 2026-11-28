import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from django.core.exceptions import ValidationError
from django.db import transaction

from accounting.services import lock_books

from .costing import allocate_landed_cost, validate_decimal
from .models import StockCut, StockCutOutput, StockLot, StockMovement
from .stock import record_stock_movement, validate_stock_input
from .valuation import value_stock_movement


MAX_CUT_OUTPUTS = 12
TRACE_FIELDS = ("grade", "heat_number", "batch_number", "mill_name", "manufacturer_name")


@dataclass(frozen=True)
class CutOutput:
    kind: str
    lot_id: int
    location_id: int
    quantity: Decimal
    actual_kg: Decimal


@transaction.atomic
def record_stock_cut(workspace, actor, *, lot_id, source_id, quantity, actual_kg, posted_on, reference, submission_key,
                     outputs):
    lock_books(workspace, actor)
    lots = StockLot.objects.filter(workspace=workspace, product__owner_id=workspace.owner_id)
    source = lots.filter(pk=lot_id).first()
    if source is None:
        raise ValidationError("Choose an input lot from this company.")
    reference = validate_stock_input(source, quantity, posted_on, reference, submission_key)
    validate_decimal(actual_kg, digits=18, places=6, label="measured input weight", positive=True)
    outputs = tuple(outputs)
    if not 1 <= len(outputs) <= MAX_CUT_OUTPUTS:
        raise ValidationError(f"Enter between one and {MAX_CUT_OUTPUTS} cut outputs.")
    lot_ids = {part.lot_id for part in outputs}
    if lot_id in lot_ids or len(lot_ids) != len(outputs):
        raise ValidationError("Use a distinct output lot for each cut result.")
    destinations = lots.in_bulk(lot_ids)
    for part in outputs:
        target = destinations.get(part.lot_id)
        if target is None or part.kind not in StockCutOutput.Kind.values:
            raise ValidationError("Choose a valid output type and lot from this company.")
        if any(getattr(source, key) != getattr(target, key) for key in TRACE_FIELDS):
            raise ValidationError("Output lots must preserve the input lot's grade and mill traceability.")
        if StockCutOutput.objects.filter(receipt__movement__lot=target).exclude(kind=part.kind).exists():
            raise ValidationError("An output lot must keep its original cut classification.")
        validate_stock_input(target, part.quantity, posted_on, reference, submission_key)
        validate_decimal(part.actual_kg, digits=18, places=6, label="measured output weight", positive=True)
    if sum(part.actual_kg for part in outputs) != actual_kg:
        raise ValidationError("Measured output weights, including recovered scrap, must equal the measured input weight.")

    def number(value):
        return format(value.normalize(), "f")

    fingerprint = hashlib.sha256(json.dumps([
        lot_id, source_id, number(quantity), number(actual_kg), posted_on.isoformat(), reference,
        [(part.kind, part.lot_id, part.location_id, number(part.quantity), number(part.actual_kg)) for part in outputs],
    ]).encode()).hexdigest()
    previous = StockCut.objects.filter(workspace=workspace, submission_key=submission_key).first()
    if previous:
        if previous.fingerprint != fingerprint:
            raise ValidationError("This submission key already belongs to a different cut.")
        return previous

    input_move = record_stock_movement(
        workspace, actor, lot_id=source.pk, source_id=source_id, kind=StockMovement.Kind.ISSUE,
        quantity=quantity, actual_kg=actual_kg, posted_on=posted_on, reference=reference,
        submission_key=uuid5(NAMESPACE_URL, f"steel-quotes/cut/{workspace.pk}/{submission_key}/input"),
    )
    cost = value_stock_movement(workspace, actor, movement_id=input_move.pk)
    cut = StockCut.objects.create(workspace=workspace, source=cost, fingerprint=fingerprint,
                                  submission_key=submission_key, recorded_by=actor)
    portions = allocate_landed_cost(cost.amount, (part.actual_kg for part in outputs))
    for part, amount in zip(outputs, portions):
        receipt = record_stock_movement(
            workspace, actor, lot_id=part.lot_id, destination_id=part.location_id, kind=StockMovement.Kind.RECEIPT,
            quantity=part.quantity, actual_kg=part.actual_kg, posted_on=posted_on, reference=reference,
            submission_key=uuid5(NAMESPACE_URL, f"steel-quotes/cut/{workspace.pk}/{submission_key}/{part.lot_id}"),
        )
        valued = value_stock_movement(workspace, actor, movement_id=receipt.pk, material=amount)
        StockCutOutput.objects.create(cut=cut, receipt=valued, kind=part.kind)
    return cut
