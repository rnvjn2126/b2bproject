from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

from accounting.models import AccountGroup, Ledger

from .models import InvoiceDraft
from .tax import check_decimal


GST_COMPONENTS = ("cgst", "sgst", "utgst", "igst", "cess")


def plan_invoice_posting(draft, *, recoverable_input_tax=None):
    """Return (ledger role, side, amount) proposals. No journal is created."""
    sales = draft.kind == InvoiceDraft.Kind.SALES
    if sales:
        if recoverable_input_tax is not None:
            raise ValidationError("Input tax treatment applies only to purchase invoices.")
    elif draft.kind != InvoiceDraft.Kind.PURCHASE or not isinstance(recoverable_input_tax, bool):
        raise ValidationError("Explicitly confirm the purchase input tax treatment.")

    try:
        tax = draft.snapshot["tax"]
        amounts = [tax[component] for component in ("taxable", *GST_COMPONENTS)]
        amounts.append(draft.snapshot["round_off"])
        if any(not isinstance(amount, str) for amount in amounts):
            raise TypeError
        taxable, cgst, sgst, utgst, igst, cess, round_off = map(Decimal, amounts)
    except (KeyError, TypeError, InvalidOperation):
        raise ValidationError("The invoice snapshot is missing valid amounts.") from None

    check_decimal(draft.total, 15, 2)
    check_decimal(round_off, 5, 2)
    tax_amounts = (cgst, sgst, utgst, igst, cess)
    for amount in (taxable, *tax_amounts):
        check_decimal(amount, 15, 2)
        if amount < 0:
            raise ValidationError("Invoice tax and taxable amounts cannot be negative.")
    if (igst and (cgst or sgst or utgst)) or (sgst and utgst):
        raise ValidationError("The invoice snapshot combines incompatible GST components.")
    tax_total = sum(tax_amounts, Decimal(0))
    if draft.total <= 0 or draft.total != taxable + tax_total + round_off:
        raise ValidationError("The invoice total must be positive and match its components.")

    # Round-off follows the material side when it increases the amount due.
    balance_side, material_side = ("D", "C") if sales else ("C", "D")
    lines = [("receivable" if sales else "payable", balance_side, draft.total)]
    if not sales and not recoverable_input_tax:
        taxable += tax_total
    if taxable:
        check_decimal(taxable, 15, 2)
        lines.append(("sales" if sales else "purchases", material_side, taxable))
    if sales or recoverable_input_tax:
        prefix = "output" if sales else "input"
        lines.extend((f"{prefix}_{component}", material_side, amount)
                     for component, amount in zip(GST_COMPONENTS, tax_amounts) if amount)
    if round_off:
        lines.append(("round_off", material_side if round_off > 0 else balance_side, abs(round_off)))
    return lines


def resolve_invoice_lines(workspace, draft, ledger_ids, *, recoverable_input_tax=None):
    """Bind a proposal to distinct ledgers in this company without posting it."""
    if draft.workspace_id != workspace.pk:
        raise ValidationError("Choose an invoice draft in your workspace.")
    plan = plan_invoice_posting(draft, recoverable_input_tax=recoverable_input_tax)
    required = {role: ledger_ids.get(role) for role, _, _ in plan}
    if any(type(pk) is not int or pk <= 0 for pk in required.values()):
        raise ValidationError("Choose a ledger for every required invoice role.")
    if len(set(required.values())) != len(required):
        raise ValidationError("Choose distinct ledgers for the required invoice roles.")

    ledgers = Ledger.objects.filter(workspace=workspace, group__workspace=workspace).select_related("group")
    ledgers = ledgers.in_bulk(required.values())
    kind = AccountGroup.Kind
    allowed = {
        "receivable": {kind.ASSET}, "payable": {kind.LIABILITY}, "sales": {kind.INCOME},
        "purchases": {kind.ASSET, kind.EXPENSE}, "round_off": {kind.INCOME, kind.EXPENSE},
        **{f"input_{component}": {kind.ASSET} for component in GST_COMPONENTS},
        **{f"output_{component}": {kind.LIABILITY} for component in GST_COMPONENTS},
    }
    for role, pk in required.items():
        ledger = ledgers.get(pk)
        if ledger is None or ledger.group.kind not in allowed[role]:
            raise ValidationError("An invoice ledger is unavailable or has the wrong account classification.")
    return [(ledgers[required[role]], side, amount) for role, side, amount in plan]
