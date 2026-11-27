from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import DecimalValidator

from dashboard.models import Product


PI = Decimal("3.141592653589793238462643383")
MM2_PER_M2 = Decimal("1000000")
MM_PER_M = Decimal("1000")
KG_PER_TONNE = Decimal("1000")


def _positive(name, value, *, allow_zero=False):
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0 or (not allow_zero and value == 0):
        raise ValidationError(f"Enter a valid {name}.")
    return value


def cross_section_mm2(profile, *, diameter=None, width=None, depth=None, thickness=None, flange=None):
    if profile in ("round", "tmt", "pipe"):
        diameter = _positive("diameter", diameter)
        if profile != "pipe":
            return PI * diameter ** 2 / 4
        thickness = _positive("wall thickness", thickness)
        if thickness * 2 >= diameter:
            raise ValidationError("Pipe wall thickness must leave a positive inside diameter.")
        return PI * thickness * (diameter - thickness)

    if profile not in ("sheet", "plate", "coil", "angle", "channel", "beam"):
        raise ValidationError("Choose a supported steel profile.")
    width = _positive("width", width)
    thickness = _positive("thickness", thickness)
    if profile in ("sheet", "plate", "coil"):
        return width * thickness
    depth = _positive("depth or second leg length", depth)
    if profile == "angle":
        if thickness >= min(width, depth):
            raise ValidationError("Angle thickness must be smaller than both legs.")
        return thickness * (width + depth - thickness)
    flange = _positive("flange thickness", flange)
    if flange * 2 >= depth or thickness >= width:
        raise ValidationError("The section must leave a positive web depth and flange width.")
    return thickness * (depth - 2 * flange) + 2 * width * flange


def convert_quantity(quantity, source, target, *, specification=None, measured_kg_per_m=None):
    """Convert without rounding so callers can apply the precision of their records."""
    quantity = _positive("quantity", quantity, allow_zero=True)
    DecimalValidator(18, 6)(quantity)
    unit = Product.Unit
    if source not in unit.values or target not in unit.values:
        raise ValidationError("Choose a supported quantity unit.")
    if source == target:
        return quantity

    mass_units = {unit.KG, unit.TONNE}
    if source in mass_units and target in mass_units:
        return quantity * KG_PER_TONNE if source == unit.TONNE else quantity / KG_PER_TONNE

    length = None
    if unit.PIECE in (source, target):
        if specification is None:
            raise ValidationError("Set a length per piece before converting pieces.")
        length = _positive("length per piece", specification.length_mm) / MM_PER_M

    if source not in mass_units and target not in mass_units:
        return quantity * length if source == unit.PIECE else quantity / length

    if measured_kg_per_m is not None:
        kg_per_m = _positive("measured kilograms per metre", measured_kg_per_m)
    elif specification is not None:
        kg_per_m = specification.theoretical_kg_per_m
    else:
        raise ValidationError("Record a measured weight per metre or a steel specification for this conversion.")

    factors = {unit.KG: Decimal(1), unit.TONNE: KG_PER_TONNE, unit.METRE: kg_per_m}
    if length is not None:
        factors[unit.PIECE] = kg_per_m * length
    return quantity * factors[source] / factors[target]
