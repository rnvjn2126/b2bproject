from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from itertools import groupby

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from dashboard.models import BusinessAccount
from inventory.reconciliation import reconcile_stock_to_ledger, stock_asset_ledgers
from invoicing.models import InvoiceDraft, IssuedInvoice
from settlements.balances import invoice_balances

from .models import AccountGroup, Journal, JournalLine, Ledger
from .services import funds_ledgers
from .statements import financial_statements


ZERO = Decimal("0.00")
CURRENT_ASSET_GROUPS = {"ASSET-1", "ASSET-3", "ASSET-4", "ASSET-5", "ASSET-6"}
CURRENT_LIABILITY_GROUPS = {"LIABILITY-1", "LIABILITY-4", "LIABILITY-5"}
LOAN_GROUPS = {"LIABILITY-2", "LIABILITY-3"}
CASH_FLOW_SECTIONS = (("operating", "Operating"), ("investing", "Investing"), ("financing", "Financing"),
                      ("review", "Needs classification"))
KINDS = AccountGroup.Kind


def comparison_dates(start, end, mode):
    if mode == "previous":
        previous = start - timedelta(days=(end - start).days + 1), start - timedelta(days=1)
        return previous if previous[0].year >= 1900 else None
    if mode == "prior-year" and start.year > 1900:
        def prior(day):
            year = day.year - 1
            return date(year, day.month, min(day.day, 28)) if day.month == 2 and day.day == 29 else day.replace(year=year)
        return prior(start), prior(end)
    return None


def period_lines(workspace, end):
    return JournalLine.objects.filter(
        journal__workspace=workspace, journal__sealed=True, journal__date__lte=end,
        ledger__workspace=workspace, ledger__group__workspace=workspace,
    )


def _group_codes(workspace):
    groups = {pk: (code, parent) for pk, code, parent in AccountGroup.objects.filter(workspace=workspace)
              .values_list("pk", "code", "parent_id")}
    result = {}
    for pk in groups:
        codes = set()
        node = pk
        while node in groups and groups[node][0] not in codes:
            code, node = groups[node]
            codes.add(code)
        result[pk] = codes
    return result


def _category(kind, codes):
    if kind == KINDS.ASSET and "ASSET-2" in codes:
        return "investing"
    if kind == KINDS.EQUITY or (kind == KINDS.LIABILITY and codes & LOAN_GROUPS):
        return "financing"
    if (kind in (KINDS.INCOME, KINDS.EXPENSE)
            or (kind == KINDS.ASSET and codes & CURRENT_ASSET_GROUPS)
            or (kind == KINDS.LIABILITY and codes & CURRENT_LIABILITY_GROUPS)):
        return "operating"
    return "review"


def cash_flow(workspace, start, end, group_codes):
    cash_ids = set(funds_ledgers(workspace).values_list("pk", flat=True))
    base = period_lines(workspace, end)
    journal_ids = base.filter(ledger_id__in=cash_ids).values("journal_id")
    journal_lines = base.filter(journal_id__in=journal_ids).order_by("journal__date", "journal_id", "pk").values_list(
        "journal_id", "journal__date", "journal__kind", "journal__reverses__kind",
        "ledger_id", "ledger__group_id", "ledger__group__kind", "side", "amount",
    )
    flows = {key: {"label": label, "inflow": ZERO, "outflow": ZERO, "journal_count": 0}
             for key, label in CASH_FLOW_SECTIONS}
    opening = setup = ZERO
    for _, records in groupby(journal_lines.iterator(), key=lambda line: line[0]):
        cash = ZERO
        classifications = set()
        for _, day, kind, original_kind, ledger, group, account_kind, side, amount in records:
            if ledger in cash_ids:
                cash += amount if side == JournalLine.Side.DEBIT else -amount
            else:
                classifications.add(_category(account_kind, group_codes[group]))
        if not cash:
            continue
        if day < start:
            opening += cash
        elif Journal.Kind.OPENING in (kind, original_kind):
            setup += cash
        else:
            key = next(iter(classifications)) if len(classifications) == 1 else "review"
            bucket = flows[key]
            bucket["inflow" if cash > 0 else "outflow"] += abs(cash)
            bucket["journal_count"] += 1
    for row in flows.values():
        row["net"] = row["inflow"] - row["outflow"]
    movement = sum((row["net"] for row in flows.values()), ZERO)
    return {"opening": opening, "opening_adjustments": setup, "flows": tuple(flows.values()), "movement": movement,
            "closing": opening + setup + movement, "unclassified": flows["review"]["journal_count"]}


def _working_capital(statements, chart):
    assets, liabilities, _ = statements["balance_sheet"]
    current_assets = sum((row["amount"] for row in assets["rows"] if chart[row["code"]] & CURRENT_ASSET_GROUPS), ZERO)
    current_liabilities = sum((row["amount"] for row in liabilities["rows"]
                               if chart[row["code"]] & CURRENT_LIABILITY_GROUPS), ZERO)
    unclassified_assets = sum((row["amount"] for row in assets["rows"] if not chart[row["code"]] & CURRENT_ASSET_GROUPS
                               and "ASSET-2" not in chart[row["code"]]), ZERO)
    unclassified_liabilities = sum((row["amount"] for row in liabilities["rows"]
                                    if not chart[row["code"]] & (CURRENT_LIABILITY_GROUPS | LOAN_GROUPS)), ZERO)
    return {"assets": current_assets, "liabilities": current_liabilities, "net": current_assets - current_liabilities,
            "other_assets": unclassified_assets, "other_liabilities": unclassified_liabilities}


@transaction.atomic
def financial_overview(workspace, actor, start, end):
    if workspace.owner_id != actor.pk or not actor.is_active:
        raise PermissionDenied
    if type(start) is not date or type(end) is not date or not start <= end <= timezone.localdate():
        raise ValidationError("Choose a valid report period through today.")
    # A read snapshot keeps reports aligned with the workspace posting lock.
    BusinessAccount.objects.select_for_update(of=("self",)).only("pk").get(pk=workspace.pk, owner=actor, owner__is_active=True)
    statements = financial_statements(workspace, start, end)
    chart_groups = _group_codes(workspace)
    chart = {code: chart_groups[group] for code, group in Ledger.objects.filter(
        workspace=workspace, group__workspace=workspace,
    ).values_list("code", "group_id")}
    income, expense = statements["profit_loss"]
    sales = sum((row["amount"] for row in income["rows"] if "INCOME-1" in chart[row["code"]]), ZERO)
    cost_lines = period_lines(workspace, end).filter(
        journal__date__gte=start, ledger__group__kind=KINDS.EXPENSE,
    ).filter(
        Q(journal__sale_cost__invoice__workspace=workspace) | Q(journal__salecostcorrection__sale_cost__invoice__workspace=workspace),
    ).values_list("side", "amount")
    cogs = sum((amount if side == JournalLine.Side.DEBIT else -amount for side, amount in cost_lines.iterator()), ZERO)

    invoice_totals = defaultdict(Decimal)
    past_due = ZERO
    for row in invoice_balances(workspace, end):
        if row.outstanding > 0:
            invoice_totals[row.invoice.kind] += row.outstanding
            if row.due_on and row.due_on < end and row.invoice.kind == InvoiceDraft.Kind.SALES:
                past_due += row.outstanding
    uncosted_sales = IssuedInvoice.objects.filter(
        workspace=workspace, journal__workspace=workspace, journal__sealed=True, kind=InvoiceDraft.Kind.SALES,
        posting_on__range=(start, end), sale_cost__isnull=True,
    ).exclude(cancellation__reversal__sealed=True, cancellation__reversal__date__lte=end).count()
    stock_ledger = stock_asset_ledgers(workspace).filter(code="1200").first()
    stock = reconcile_stock_to_ledger(workspace, actor, ledger_id=stock_ledger.pk, as_of=end) if stock_ledger else None
    return {
        "start": start, "end": end, "statements": statements, "income": income["total"], "expenses": expense["total"],
        "sales": sales, "cogs": cogs, "gross": sales - cogs, "uncosted_sales": uncosted_sales,
        "cash": cash_flow(workspace, start, end, chart_groups), "working_capital": _working_capital(statements, chart),
        "receivables": invoice_totals["sales"], "payables": invoice_totals["purchase"], "past_due": past_due, "stock": stock,
    }
