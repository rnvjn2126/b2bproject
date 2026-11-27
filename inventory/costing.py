from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, localcontext

from django.core.exceptions import ValidationError
from django.core.validators import DecimalValidator
from django.db import models


PAISE = Decimal("0.01")
ZERO = Decimal("0.00")


class CostMethod(models.TextChoices):
    FIFO = "fifo", "First in, first out"
    AVERAGE = "average", "Moving weighted average"


def _validate_decimal(value, *, digits, places, label, positive=False):
    if not isinstance(value, Decimal) or not value.is_finite() or (value <= 0 if positive else value < 0):
        raise ValidationError(f"Enter a valid {label}.")
    DecimalValidator(digits, places)(value)


@dataclass(frozen=True)
class CostBalance:
    quantity: Decimal
    amount: Decimal

    def __post_init__(self):
        _validate_decimal(self.quantity, digits=18, places=3, label="stock quantity", positive=True)
        _validate_decimal(self.amount, digits=18, places=2, label="stock value")


def _split(balance, quantity):
    if quantity == balance.quantity:
        return balance.amount, None
    with localcontext() as context:
        context.prec = 48
        amount = (balance.amount * quantity / balance.quantity).quantize(PAISE, rounding=ROUND_HALF_UP)
    return amount, CostBalance(balance.quantity - quantity, balance.amount - amount)


def consume_stock(method, layers, quantity):
    """Price an issue and return its cost and the remaining balances in input order.

    FIFO layers arrive oldest first. A moving-average pool has one quantity and
    value, irrespective of the number of existing receipts.
    """
    _validate_decimal(quantity, digits=14, places=3, label="issue quantity", positive=True)
    layers = tuple(layers)
    if method not in CostMethod.values or (method == CostMethod.AVERAGE and len(layers) > 1):
        raise ValidationError("Choose a valid valuation method and stock pool.")
    if quantity > sum(layer.quantity for layer in layers):
        raise ValidationError("The issue exceeds the quantity available for valuation.")

    remaining = []
    cost = ZERO
    for layer in layers:
        if quantity == 0:
            remaining.append(layer)
            continue
        taken = min(quantity, layer.quantity)
        share, balance = _split(layer, taken)
        cost += share
        quantity -= taken
        if balance is not None:
            remaining.append(balance)
    return cost, tuple(remaining)


def allocate_landed_cost(amount, weights):
    """Distribute one charge to ordered receipt lines without losing a paisa."""
    _validate_decimal(amount, digits=15, places=2, label="landed cost")
    weights = tuple(weights)
    if not weights:
        raise ValidationError("Choose at least one line for landed cost allocation.")
    for weight in weights:
        _validate_decimal(weight, digits=18, places=6, label="allocation weight")
    total = sum(weights)
    if not total:
        raise ValidationError("At least one allocation weight must be positive.")
    with localcontext() as context:
        context.prec = 48
        exact = [amount * weight / total for weight in weights]
        shares = [share.quantize(PAISE, rounding=ROUND_DOWN) for share in exact]
        cents = int((amount - sum(shares)) / PAISE)
        # Give leftover paise to the largest fractions, preserving order for ties.
        by_remainder = sorted(range(len(weights)), key=lambda index: exact[index] - shares[index], reverse=True)
        for index in by_remainder[:cents]:
            shares[index] += PAISE
    return tuple(shares)
