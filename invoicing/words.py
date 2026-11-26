from django.core.exceptions import ValidationError

from .tax import check_decimal


SMALL = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
)
TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
INDIAN_GROUPS = ((10_000_000, "crore"), (100_000, "lakh"), (1_000, "thousand"), (100, "hundred"))


def integer_words(value):
    for factor, label in INDIAN_GROUPS:
        if value >= factor:
            count, remainder = divmod(value, factor)
            tail = f" {integer_words(remainder)}" if remainder else ""
            return f"{integer_words(count)} {label}{tail}"
    if value < 20:
        return SMALL[value]
    tens, ones = divmod(value, 10)
    return TENS[tens] + (f" {SMALL[ones]}" if ones else "")


def rupees_in_words(amount):
    check_decimal(amount, 15, 2)
    if amount < 0:
        raise ValidationError("Expected a nonnegative invoice amount.")
    rupees, paise = divmod(int(amount * 100), 100)
    result = f"{integer_words(rupees)} {'rupee' if rupees == 1 else 'rupees'}"
    if paise:
        result += f" and {integer_words(paise)} {'paisa' if paise == 1 else 'paise'}"
    return result.capitalize() + " only"
