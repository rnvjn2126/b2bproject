from collections import defaultdict
from decimal import Decimal

from .models import AccountGroup, JournalLine


def financial_statements(workspace, start, end, branch=None):
    """Build statements from posted lines, retaining exact Decimal totals on SQLite."""
    lines = JournalLine.objects.filter(
        journal__workspace=workspace,
        ledger__workspace=workspace,
        ledger__group__workspace=workspace,
        journal__date__lte=end,
    )
    if branch:
        lines = lines.filter(journal__branch=branch)

    closing = defaultdict(Decimal)
    movements = defaultdict(Decimal)
    kinds = AccountGroup.Kind
    for code, name, kind, day, side, amount in lines.order_by().values_list(
        "ledger__code", "ledger__name", "ledger__group__kind", "journal__date", "side", "amount",
    ).iterator():
        key = code, name, kind
        debit_normal = kind in (kinds.ASSET, kinds.EXPENSE)
        signed = amount if (side == JournalLine.Side.DEBIT) == debit_normal else -amount
        closing[key] += signed
        if day >= start and kind in (kinds.INCOME, kinds.EXPENSE):
            movements[key] += signed

    def sections(balances, account_kinds):
        result = [{"label": kind.label, "total": Decimal(0), "rows": []} for kind in account_kinds]
        groups = dict(zip(account_kinds, result))
        for (code, name, kind), amount in sorted(balances.items()):
            if kind in groups:
                groups[kind]["rows"].append({"code": code, "name": name, "amount": amount})
                groups[kind]["total"] += amount
        return result

    balance_sheet = sections(closing, (kinds.ASSET, kinds.LIABILITY, kinds.EQUITY))
    profit_loss = sections(movements, (kinds.INCOME, kinds.EXPENSE))
    accumulated_result = sum(
        (amount if kind == kinds.INCOME else -amount for (_, _, kind), amount in closing.items()
         if kind in (kinds.INCOME, kinds.EXPENSE)),
        Decimal(0),
    )
    liabilities_and_equity = balance_sheet[1]["total"] + balance_sheet[2]["total"] + accumulated_result
    return {
        "balance_sheet": balance_sheet,
        "profit_loss": profit_loss,
        "net_result": profit_loss[0]["total"] - profit_loss[1]["total"],
        "accumulated_result": accumulated_result,
        "liabilities_and_equity": liabilities_and_equity,
        "difference": balance_sheet[0]["total"] - liabilities_and_equity,
    }
