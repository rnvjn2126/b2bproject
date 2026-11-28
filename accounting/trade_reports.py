from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Prefetch

from invoicing.models import InvoiceDraft, InvoiceReturn, IssuedInvoice

from .models import Journal, JournalLine
from .reporting import ZERO, period_lines


@dataclass(frozen=True)
class TradeEntry:
    date: date
    invoice_id: int
    invoice_number: str
    journal_id: int
    journal_reference: str
    event: str
    party_key: tuple
    party: str
    product_key: tuple
    product: str
    unit: str
    quantity: Decimal
    trade_amount: Decimal
    tax_posted: Decimal
    invoice_amount: Decimal
    cost: Decimal | None


def _cost_amount(link, field, workspace, on):
    if link is None:
        return None
    amount = getattr(link, field).amount
    if not amount and link.journal_id is None:
        return ZERO
    if (link.journal_id and link.journal.workspace_id == workspace.pk
            and link.journal.date == on and link.journal.sealed):
        return amount
    return None


def trade_register(workspace, kind, start, end):
    sales = kind == InvoiceDraft.Kind.SALES
    original_kind = Journal.Kind.SALES_INVOICE if sales else Journal.Kind.PURCHASE_INVOICE
    return_kind = Journal.Kind.SALES_RETURN if sales else Journal.Kind.PURCHASE_RETURN
    documents = IssuedInvoice.objects.filter(
        workspace=workspace, draft__workspace=workspace, posting_on__lte=end, kind=kind,
        journal__sealed=True, journal__workspace=workspace, journal__kind=original_kind,
    )
    returns = InvoiceReturn.objects.filter(
        journal__workspace=workspace, journal__sealed=True, journal__kind=return_kind, journal__date__range=(start, end),
    )
    invoice_fields = [
        "journal", "cancellation__reversal", "draft__movement__sales_line__order",
        "draft__movement__purchase_order",
    ]
    if sales:
        invoice_fields += ["sale_cost__issue", "sale_cost__journal",
                           "cancellation__salecostcorrection__receipt", "cancellation__salecostcorrection__journal"]
        returns = returns.select_related("salecostcorrection__receipt", "salecostcorrection__journal")
    documents = documents.select_related(*invoice_fields).prefetch_related(Prefetch(
        "returns", queryset=returns.select_related("journal"), to_attr="report_returns",
    ))
    entries = []
    for document in documents:
        item = document.snapshot["item"]
        quantity = Decimal(item["quantity"])
        if start <= document.journal.date <= end:
            link = getattr(document, "sale_cost", None) if sales else None
            cost = _cost_amount(link, "issue", workspace, document.journal.date)
            entries.append((document, document.journal, "Invoice", quantity, cost))
        cancellation = getattr(document, "cancellation", None)
        if cancellation:
            reverse = cancellation.reversal
            if (reverse.workspace_id == workspace.pk and reverse.sealed
                    and reverse.reverses_id == document.journal_id and start <= reverse.date <= end):
                link = getattr(cancellation, "salecostcorrection", None) if sales else None
                cost = _cost_amount(link, "receipt", workspace, reverse.date)
                entries.append((document, reverse, "Cancellation", -quantity, -cost if cost is not None else None))
        for returned in document.report_returns:
            link = getattr(returned, "salecostcorrection", None) if sales else None
            cost = _cost_amount(link, "receipt", workspace, returned.journal.date)
            entries.append((document, returned.journal, "Return", -returned.quantity, -cost if cost is not None else None))

    lines = defaultdict(lambda: defaultdict(Decimal))
    journals = {journal.pk for _, journal, _, _, _ in entries}
    for journal, ledger, side, amount in period_lines(workspace, end).filter(journal_id__in=journals).values_list(
        "journal_id", "ledger_id", "side", "amount",
    ).iterator():
        lines[journal][ledger] += amount if side == JournalLine.Side.DEBIT else -amount

    result = []
    for invoice, journal, event, quantity, cost in entries:
        movement = invoice.draft.movement
        party = invoice.snapshot["party"]["name"]
        party_id = movement.sales_line.order.customer_id if sales else movement.purchase_order.supplier_id
        item = invoice.snapshot["item"]
        product = item.get("catalogue_name") or " · ".join(
            value for value in (item["description"], item.get("grade"), item.get("dimensions")) if value
        )
        product_key = ("catalogue", item["catalogue_id"]) if item.get("catalogue_id") else ("description", product)
        roles = invoice.ledger_ids
        amounts = lines[journal.pk]
        sign = -1 if sales else 1
        prefix = "output_" if sales else "input_"
        result.append(TradeEntry(
            journal.date, invoice.pk, invoice.number, journal.pk, journal.transaction_reference, event,
            ("party", party_id), str(party), product_key, product, item["unit"], quantity,
            sign * amounts[roles.get("sales" if sales else "purchases")],
            sign * sum((amounts[pk] for role, pk in roles.items() if role.startswith(prefix)), ZERO),
            -sign * amounts[roles["receivable" if sales else "payable"]], cost,
        ))
    return sorted(result, key=lambda row: (row.date, row.journal_id), reverse=True)


@dataclass
class Profitability:
    name: str
    revenue: Decimal = ZERO
    known_cost: Decimal = ZERO
    matched_revenue: Decimal = ZERO
    missing_cost: int = 0

    @property
    def matched_gross(self):
        return self.matched_revenue - self.known_cost


def profitability(rows, by):
    result = {}
    for row in rows:
        key, label = (row.party_key, row.party) if by == "customer" else (row.product_key, row.product)
        if key not in result:
            result[key] = Profitability(label)
        group = result[key]
        group.revenue += row.trade_amount
        if row.cost is None:
            group.missing_cost += 1
        else:
            group.matched_revenue += row.trade_amount
            group.known_cost += row.cost
    return sorted(result.values(), key=lambda group: (-group.revenue, group.name))
