from decimal import Decimal

from django import template


register = template.Library()


@register.filter
def inr(value):
    if value is None:
        return "—"
    amount = Decimal(value)
    whole, fraction = f"{abs(amount):.2f}".split(".")
    if len(whole) > 3:
        groups = [whole[-3:]]
        remaining = whole[:-3]
        while remaining:
            groups.append(remaining[-2:])
            remaining = remaining[:-2]
        whole = ",".join(reversed(groups))
    return f"{'−' if amount < 0 else ''}₹{whole}.{fraction}"
