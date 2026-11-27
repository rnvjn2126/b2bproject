from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from accounting.services import lock_books

from .costing import ZERO, CostBalance, CostMethod, consume_stock, validate_decimal
from .models import StockMovement, ValuationEvent, ValuationLayer, ValuationPolicy


@transaction.atomic
def set_valuation_method(workspace, actor, *, method):
    lock_books(workspace, actor)
    if method not in CostMethod.values:
        raise ValidationError("Choose a valid inventory valuation method.")
    policy, _ = ValuationPolicy.objects.get_or_create(workspace=workspace, defaults={"method": method})
    if policy.method != method:
        if ValuationEvent.objects.filter(movement__workspace=workspace).exists():
            raise ValidationError("Review a formal transition before changing a method already used for valuation.")
        policy.method = method
        policy.save(update_fields=["method"])
    return policy


def _fifo_issue(events, quantity, closing_quantity, closing_amount):
    layers = list(ValuationLayer.objects.filter(receipt__in=events, quantity__gt=0)
                  .order_by("receipt__movement__posted_on", "receipt__movement_id"))
    if (sum(layer.quantity for layer in layers), sum(layer.amount for layer in layers)) != (
        closing_quantity, closing_amount,
    ):
        raise ValidationError("The FIFO layers do not reconcile to the last valuation.")
    cost, remaining = consume_stock(CostMethod.FIFO, (CostBalance(layer.quantity, layer.amount) for layer in layers),
                                    quantity)
    exhausted = len(layers) - len(remaining)
    # Unconsumed FIFO layers are a suffix. Only the first remaining layer may be reduced.
    for layer in layers[:exhausted]:
        layer.quantity, layer.amount = Decimal(0), ZERO
        layer.save(update_fields=["quantity", "amount"])
    if remaining:
        layer = layers[exhausted]
        if (layer.quantity, layer.amount) != (remaining[0].quantity, remaining[0].amount):
            layer.quantity, layer.amount = remaining[0].quantity, remaining[0].amount
            layer.save(update_fields=["quantity", "amount"])
    return cost


@transaction.atomic
def value_stock_movement(workspace, actor, *, movement_id, material=None, freight=ZERO, packaging=ZERO, other=ZERO):
    """Append a valuation snapshot. Monetary journal posting is a separate workflow."""
    lock_books(workspace, actor)
    movements = StockMovement.objects.filter(workspace=workspace, lot__workspace=workspace,
                                             lot__product__owner_id=workspace.owner_id)
    movement = movements.filter(pk=movement_id).select_related("lot").first()
    if movement is None:
        raise ValidationError("Choose a stock movement in this company.")
    is_receipt = movement.kind == StockMovement.Kind.RECEIPT
    if is_receipt and material is None:
        raise ValidationError("Enter the receipt material cost explicitly, including zero when appropriate.")
    cost_components = (ZERO if material is None else material, freight, packaging, other)
    for value in cost_components:
        validate_decimal(value, digits=15, places=2, label="receipt cost")
    if not is_receipt and any(cost_components):
        raise ValidationError("Only a receipt can introduce additional cost.")
    prior = ValuationEvent.objects.filter(movement=movement).first()
    if prior:
        if (prior.material, prior.freight, prior.packaging, prior.other) != cost_components:
            raise ValidationError("This movement has already been valued with different costs.")
        return prior
    if movement.kind not in StockMovement.Kind.values:
        raise ValidationError("Choose a supported stock movement.")

    method = ValuationPolicy.objects.filter(workspace=workspace).values_list("method", flat=True).first()
    if method is None:
        raise ValidationError("Set this company's inventory valuation method first.")

    movements = movements.filter(lot__product_id=movement.lot.product_id, lot__unit=movement.lot.unit)
    earlier = Q(posted_on__lt=movement.posted_on) | Q(posted_on=movement.posted_on, pk__lt=movement.pk)
    if movements.filter(earlier, valuation__isnull=True).exists():
        raise ValidationError("Value earlier stock movements for the same product and unit first.")

    events = ValuationEvent.objects.filter(movement__in=movements)
    last = events.order_by("-movement__posted_on", "-movement_id").first()
    if last and (last.method != method or (last.movement.posted_on, last.movement_id) >= (movement.posted_on, movement.pk)):
        raise ValidationError("The valuation would change a previously valued movement.")
    closing_quantity = last.closing_quantity if last else Decimal(0)
    closing_amount = last.closing_amount if last else ZERO
    amount = ZERO
    if is_receipt:
        amount = sum(cost_components, ZERO)
        closing_quantity += movement.quantity
        closing_amount += amount
    elif movement.kind == StockMovement.Kind.ISSUE:
        if method == CostMethod.FIFO:
            amount = _fifo_issue(events, movement.quantity, closing_quantity, closing_amount)
        else:
            balances = [CostBalance(closing_quantity, closing_amount)] if closing_quantity else []
            amount, _ = consume_stock(method, balances, movement.quantity)
        closing_quantity -= movement.quantity
        closing_amount -= amount
    # Transfers stay inside a company-wide cost pool and leave its value unchanged.
    validate_decimal(amount, digits=15, places=2, label="valuation amount")
    validate_decimal(closing_quantity, digits=18, places=3, label="closing quantity")
    validate_decimal(closing_amount, digits=18, places=2, label="closing value")
    valued = ValuationEvent.objects.create(
        movement=movement, method=method, material=cost_components[0], freight=freight, packaging=packaging, other=other,
        amount=amount, closing_quantity=closing_quantity, closing_amount=closing_amount, recorded_by=actor,
    )
    if is_receipt and method == CostMethod.FIFO:
        ValuationLayer.objects.create(receipt=valued, quantity=movement.quantity, amount=amount)
    return valued
