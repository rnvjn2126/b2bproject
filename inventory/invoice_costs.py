from django.core.exceptions import ValidationError

from .purchase_costs import reverse_purchase_cost
from .sale_costs import restore_sale_cost


def apply_inventory_cost_correction(workspace, actor, correction, restock_movement_id):
    invoice = correction.invoice
    if hasattr(invoice, "sale_cost"):
        if restock_movement_id is None:
            raise ValidationError("Choose the confirmed stock receipt for this costed invoice correction.")
        restore_sale_cost(workspace, actor, movement_id=restock_movement_id, correction=correction)
    elif hasattr(invoice, "purchase_cost"):
        if restock_movement_id is None:
            raise ValidationError("Choose the confirmed stock return issue for this costed purchase correction.")
        reverse_purchase_cost(workspace, actor, movement_id=restock_movement_id, correction=correction)
    elif restock_movement_id is not None:
        raise ValidationError("A stock movement can only be assigned to a costed invoice correction.")
    return correction
