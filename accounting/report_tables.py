from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import PermissionDenied

from invoicing.models import InvoiceDraft
from settlements.balances import invoice_balances

from .models import JournalLine
from .reporting import AGE_BUCKETS, ZERO, financial_overview, period_lines
from .statements import financial_statements
from .trade_reports import profitability, trade_register


@dataclass(frozen=True)
class ReportTable:
    title: str
    columns: tuple[str, ...]
    rows: list[tuple]


REPORT_NAMES = {
    "overview": "Finance summary",
    "cash-flow": "Cash flow",
    "balance-sheet": "Balance sheet",
    "profit-loss": "Profit and loss",
    "trial-balance": "Trial balance",
    "ledger": "General ledger",
    "day-book": "Day book",
    "sales": "Sales register",
    "purchases": "Purchase register",
    "customer-profit": "Customer profitability",
    "product-profit": "Product profitability",
    "expenses": "Expense analysis",
    "ageing": "Invoice ageing",
    "stock": "Stock valuation",
}


def _table(code, columns, rows):
    return ReportTable(REPORT_NAMES[code], tuple(columns), list(rows))


def _trade_rows(workspace, code, start, end):
    sales = code != "purchases"
    return trade_register(workspace, InvoiceDraft.Kind.SALES if sales else InvoiceDraft.Kind.PURCHASE, start, end)


def _posted_activity(workspace, code, start, end, ledger, branch):
    lines = period_lines(workspace, end)
    if branch is not None:
        lines = lines.filter(journal__branch=branch)
    if ledger is not None:
        lines = lines.filter(ledger=ledger)
    if code == "ledger":
        rows = lines.filter(journal__date__gte=start).order_by("journal__date", "journal_id", "pk").values_list(
            "journal__date", "journal_id", "ledger__code", "ledger__name", "side", "amount",
        )
        rows = [(day, f"JRN-{journal}", key, name, "Debit" if side == "D" else "Credit", amount)
                for day, journal, key, name, side, amount in rows.iterator()]
        if ledger is not None:
            before = lines.filter(journal__date__lt=start).values_list("side", "amount")
            opening = sum((amount if side == "D" else -amount for side, amount in before.iterator()), ZERO)
            closing = opening + sum((row[-1] if row[-2] == "Debit" else -row[-1] for row in rows), ZERO)
            rows = [(start, "", ledger.code, ledger.name, "Opening", opening), *rows,
                    (end, "", ledger.code, ledger.name, "Closing", closing)]
        return _table(code, ["Date", "Journal", "Ledger code", "Ledger name", "Side", "Amount (INR)"], rows)
    if code == "day-book":
        totals = defaultdict(lambda: [ZERO, ZERO])
        for day, journal, kind, reference, side, amount in lines.filter(journal__date__gte=start).order_by(
            "journal__date", "journal_id", "pk",
        ).values_list("journal__date", "journal_id", "journal__kind", "journal__reference", "side", "amount").iterator():
            totals[day, journal, kind, reference][side != JournalLine.Side.DEBIT] += amount
        return _table(code, ["Date", "Journal", "Kind", "Reference", "Debit (INR)", "Credit (INR)"], (
            (day, f"JRN-{journal}", kind, reference, *total) for (day, journal, kind, reference), total in totals.items()
        ))

    totals = defaultdict(lambda: [ZERO, ZERO, ZERO])
    for key, name, day, side, amount in lines.order_by().values_list(
        "ledger__code", "ledger__name", "journal__date", "side", "amount",
    ).iterator():
        row = totals[key, name]
        if day < start:
            row[0] += amount if side == "D" else -amount
        else:
            row[1 if side == "D" else 2] += amount
    rows = []
    for (key, name), (opening, debit, credit) in sorted(totals.items()):
        closing = opening + debit - credit
        rows.append((key, name, opening, debit, credit, max(closing, ZERO), max(-closing, ZERO)))
    rows.append(("", "Totals", *(sum((row[index] for row in rows), ZERO) for index in range(2, 7))))
    return _table(code, ["Code", "Ledger", "Opening (INR)", "Debit (INR)", "Credit (INR)",
                         "Closing debit (INR)", "Closing credit (INR)"], rows)


def report_table(workspace, actor, code, start, end, ledger=None, branch=None):
    if workspace.owner_id != actor.pk or not actor.is_active:
        raise PermissionDenied
    if code in ("trial-balance", "ledger", "day-book"):
        return _posted_activity(workspace, code, start, end, ledger, branch)
    if code in ("sales", "purchases"):
        return _table(code, [
            "Date", "Invoice", "Event", "Trading party", "Product", "Quantity", "Unit", "Trade amount (INR)",
            "Posted tax (INR)", "Control amount (INR)", "Journal",
        ], ((row.date, row.invoice_number, row.event, row.party, row.product, row.quantity, row.unit,
             row.trade_amount, row.tax_posted, row.invoice_amount, row.journal_reference)
            for row in _trade_rows(workspace, code, start, end)))
    if code in ("customer-profit", "product-profit"):
        groups = profitability(_trade_rows(workspace, code, start, end), "customer" if code == "customer-profit" else "product")
        return _table(code, ["Name", "Revenue (INR)", "Revenue with cost (INR)", "Linked cost (INR)",
                            "Matched gross profit (INR)", "Missing cost documents"], (
            (group.name, group.revenue, group.matched_revenue, group.known_cost, group.matched_gross, group.missing_cost)
            for group in groups
        ))
    if code == "ageing":
        amounts = defaultdict(Decimal)
        for row in invoice_balances(workspace, end):
            if row.outstanding > 0:
                amounts[row.bucket, row.invoice.kind] += row.outstanding
        return _table(code, ["Bucket", "Receivables (INR)", "Payables (INR)"], (
            (bucket, amounts[bucket, "sales"], amounts[bucket, "purchase"])
            for bucket in AGE_BUCKETS
        ))
    if code in ("balance-sheet", "profit-loss", "expenses"):
        statements = financial_statements(workspace, start, end, branch=branch)
        sections = statements["balance_sheet" if code == "balance-sheet" else "profit_loss"]
        if code == "expenses":
            sections = sections[1:]
        rows = [(section["label"], row["code"], row["name"], row["amount"])
                for section in sections for row in section["rows"]]
        rows += [(section["label"], "", "Total", section["total"]) for section in sections]
        if code == "balance-sheet":
            rows += [
                ("Reconciliation", "", "Accumulated ledger earnings", statements["accumulated_result"]),
                ("Reconciliation", "", "Liabilities and equity including earnings", statements["liabilities_and_equity"]),
                ("Reconciliation", "", "Difference", statements["difference"]),
            ]
        elif code == "profit-loss":
            rows.append(("Result", "", "Net profit", statements["net_result"]))
        return _table(code, ["Group", "Code", "Ledger or total", "Amount (INR)"], rows)

    data = financial_overview(workspace, actor, start, end)
    if code == "stock":
        stock = data["stock"]
        rows = [] if stock is None else (
            (row.product, row.unit, row.on_hand, row.valued_quantity, row.inventory_value, row.unvalued_movements)
            for row in stock.pools
        )
        return _table(code, ["Product", "Unit", "On hand", "Valued quantity", "Inventory (INR)", "Unvalued movements"], rows)
    cash = data["cash"]
    if code == "cash-flow":
        rows = [(row["label"], row["inflow"], row["outflow"], row["net"]) for row in cash["flows"]]
        rows += [(label, None, None, cash[key]) for label, key in (
            ("Opening cash", "opening"), ("Opening adjustments", "opening_adjustments"), ("Closing cash", "closing"),
        )]
        return _table(code, ["Activity", "Inflow (INR)", "Outflow (INR)", "Net or balance (INR)"], rows)
    return _table(code, ["Measure", "Amount (INR)"], [
        ("Posted income", data["income"]), ("Posted expenses", data["expenses"]),
        ("Linked cost of sales", data["cogs"]), ("Sales less linked stock cost", data["gross"]),
        ("Net profit", data["statements"]["net_result"]), ("Closing cash and bank", cash["closing"]),
        ("Working capital", data["working_capital"]["net"]), ("Invoice receivables", data["receivables"]),
        ("Invoice payables", data["payables"]), ("Overdue customer invoices", data["past_due"]),
        ("Stock inventory value", data["stock"].inventory_value if data["stock"] else None),
    ])
