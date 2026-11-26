import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.core.validators import DecimalValidator


PAISE = Decimal("0.01")
HUNDRED = Decimal(100)
GSTIN = re.compile(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]")
STATE_CODE = re.compile(r"[0-9]{2}")


def validate_gstin(value):
    """Check regular GSTIN shape only. Registration status requires official verification."""
    if not isinstance(value, str) or not GSTIN.fullmatch(value) or value.startswith("00"):
        raise ValidationError("Enter a 15-character GSTIN in the regular registration format.")


def rounded(value):
    return value.quantize(PAISE, rounding=ROUND_HALF_UP)


def check_decimal(value, max_digits, decimal_places):
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValidationError("Enter a finite decimal value.")
    DecimalValidator(max_digits, decimal_places)(value)


@dataclass(frozen=True)
class TaxBreakdown:
    taxable: Decimal
    cgst: Decimal
    sgst: Decimal
    utgst: Decimal
    igst: Decimal
    cess: Decimal

    @property
    def total(self):
        return self.taxable + self.cgst + self.sgst + self.utgst + self.igst + self.cess


def calculate_line(*, quantity, unit_price, discount, freight, inclusive, rate, supplier_state, place_of_supply,
                   local_component):
    """Calculate a domestic candidate line with an explicit place of supply and rate record."""
    check_decimal(quantity, 14, 3)
    check_decimal(unit_price, 14, 4)
    check_decimal(discount, 15, 2)
    check_decimal(freight, 15, 2)
    if quantity <= 0 or min(unit_price, discount, freight) < 0:
        raise ValidationError("Quantity must be positive and prices, discounts and freight cannot be negative.")
    if not all(isinstance(code, str) and code != "00" and STATE_CODE.fullmatch(code)
               for code in (supplier_state, place_of_supply)):
        raise ValidationError("Choose valid supplier and place-of-supply codes.")
    if local_component not in ("sgst", "utgst") or rate is None:
        raise ValidationError("Choose an applicable GST rate and local tax component.")

    rates = dict.fromkeys(("cgst", "sgst", "utgst", "igst"), Decimal(0))
    if supplier_state == place_of_supply:
        rates["cgst"] = rate.central_rate
        rates[local_component] = rate.local_rate
    else:
        rates["igst"] = rate.integrated_rate
    rates["cess"] = rate.cess_rate
    for component_rate in rates.values():
        check_decimal(component_rate, 7, 4)
        if not 0 <= component_rate <= HUNDRED:
            raise ValidationError("The configured component rate is outside the supported range.")

    before_discount = quantity * unit_price
    if discount > before_discount:
        raise ValidationError("The discount cannot exceed the material value.")
    amount = rounded(before_discount - discount + freight)
    denominator = HUNDRED + sum(rates.values(), Decimal(0)) if inclusive else HUNDRED
    taxes = {component: rounded(amount * percentage / denominator) for component, percentage in rates.items()}
    # Preserve the entered gross amount for inclusive prices after paise rounding.
    taxable = amount - sum(taxes.values(), Decimal(0)) if inclusive else amount
    if taxable < 0:
        raise ValidationError("The rounded tax components exceed the inclusive line amount.")
    return TaxBreakdown(taxable=taxable, **taxes)


def invoice_total(lines, round_off):
    check_decimal(round_off, 5, 2)
    total = sum((line.total for line in lines), Decimal(0)) + round_off
    if total < 0:
        raise ValidationError("Round-off cannot make the total negative.")
    return total
