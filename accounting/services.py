import hashlib
import json
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import DecimalValidator
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import AccountGroup, FinancialYear, Journal, JournalLine, Ledger, Period, VoucherDraft


STARTER_GROUPS = {
    "asset": ("Current assets", "Fixed assets", "Sundry debtors", "Bank accounts", "Cash accounts", "Input duties and taxes"),
    "liability": ("Current liabilities", "Secured loans", "Unsecured loans", "Sundry creditors", "Duties and taxes"),
    "equity": ("Capital accounts", "Reserves and surplus"),
    "income": ("Sales accounts", "Direct income", "Indirect income"),
    "expense": ("Purchase accounts", "Direct expenses", "Indirect expenses"),
}
STARTER_LEDGERS = (
    ("1000", "Cash", "Cash accounts"), ("1010", "Bank", "Bank accounts"),
    ("1100", "Sundry debtors", "Sundry debtors"), ("1200", "Stock-in-hand", "Current assets"),
    ("1300", "Input GST", "Input duties and taxes"), ("1500", "Fixed assets", "Fixed assets"),
    ("2000", "Sundry creditors", "Sundry creditors"), ("2100", "Output GST", "Duties and taxes"),
    ("2110", "Duties and taxes", "Duties and taxes"), ("2200", "Secured loans", "Secured loans"),
    ("2300", "Unsecured loans", "Unsecured loans"), ("3000", "Capital", "Capital accounts"),
    ("3100", "Reserves", "Reserves and surplus"), ("4000", "Steel sales", "Sales accounts"),
    ("4100", "Other income", "Indirect income"), ("5000", "Steel purchases", "Purchase accounts"),
    ("5100", "Freight and transportation", "Direct expenses"), ("5200", "Operating expenses", "Indirect expenses"),
    ("5210", "Discounts allowed", "Indirect expenses"), ("5220", "Round-off adjustments", "Indirect expenses"),
)
MANUAL_JOURNAL_KINDS = (Journal.Kind.GENERAL, Journal.Kind.OPENING, Journal.Kind.ADJUSTMENT)
CASH_VOUCHER_KINDS = (Journal.Kind.RECEIPT, Journal.Kind.PAYMENT, Journal.Kind.CONTRA)
CASH_LEDGER_CODES = ("1000", "1010")
TRADE_VOUCHER_KINDS = (Journal.Kind.SALES, Journal.Kind.PURCHASE, Journal.Kind.DEBIT_NOTE, Journal.Kind.CREDIT_NOTE)
INVOICE_JOURNAL_KINDS = (Journal.Kind.SALES_INVOICE, Journal.Kind.PURCHASE_INVOICE,
                         Journal.Kind.SALES_RETURN, Journal.Kind.PURCHASE_RETURN)
STOCK_JOURNAL_KINDS = (Journal.Kind.STOCK_ACQUISITION, Journal.Kind.STOCK_COST, Journal.Kind.STOCK_RETURN)
REVIEW_VOUCHER_KINDS = (Journal.Kind.GENERAL,) + CASH_VOUCHER_KINDS + TRADE_VOUCHER_KINDS


def funds_ledgers(workspace):
    return Ledger.objects.filter(
        workspace=workspace, group__workspace=workspace, group__kind=AccountGroup.Kind.ASSET,
    ).filter(Q(code__in=CASH_LEDGER_CODES) | Q(funds_account__workspace=workspace))


def lock_books(workspace, actor):
    if workspace.owner_id != actor.pk or not actor.is_active:
        raise PermissionDenied
    # A write as the first statement serializes service calls on SQLite as well as PostgreSQL.
    # Change no workspace metadata, and avoid an unlocked read-then-write upgrade on SQLite.
    from dashboard.models import BusinessAccount
    from django.db.models import F

    BusinessAccount.objects.filter(pk=workspace.pk, owner=actor).update(name=F("name"))


@transaction.atomic
def setup_books(workspace, actor, start_year):
    lock_books(workspace, actor)
    if not 1900 <= start_year <= 9998:
        raise ValidationError("Choose a year from 1900 to 9998.")
    groups = {}
    for kind, names in STARTER_GROUPS.items():
        parent, _ = AccountGroup.objects.get_or_create(workspace=workspace, code=kind.upper(), defaults={
            "name": AccountGroup.Kind(kind).label, "kind": kind,
        })
        for number, name in enumerate(names, 1):
            groups[name], _ = AccountGroup.objects.get_or_create(workspace=workspace, code=f"{kind.upper()}-{number}", defaults={
                "name": name, "kind": kind, "parent": parent,
            })
    for code, name, group in STARTER_LEDGERS:
        Ledger.objects.get_or_create(workspace=workspace, code=code, defaults={"name": name, "group": groups[group]})

    year, created = FinancialYear.objects.get_or_create(workspace=workspace, start_year=start_year)
    if created:
        months = [date(start_year + offset // 12, offset % 12 + 1, 1) for offset in range(3, 16)]
        Period.objects.bulk_create(
            Period(year=year, starts_on=start, ends_before=end) for start, end in zip(months, months[1:])
        )
    return year


@transaction.atomic
def lock_period(workspace, actor, period_id):
    lock_books(workspace, actor)
    return Period.objects.filter(pk=period_id, year__workspace=workspace, locked_at__isnull=True).update(
        locked_at=timezone.now(), locked_by=actor,
    )


@transaction.atomic
def post_journal(workspace, actor, *, date, kind, reference, narration, submission_key,
                 lines=(), branch=None, cost_centre=None, reverses=None, invoice_correction=False, stock_workflow=False):
    lock_books(workspace, actor)
    stock_allowed = stock_workflow and settings.INTERNAL_STOCK_ACCOUNTING
    if kind in STOCK_JOURNAL_KINDS and not stock_allowed:
        raise PermissionDenied("Stock journals require the inventory workflow.")
    if kind in INVOICE_JOURNAL_KINDS and not settings.INTERNAL_INVOICE_ISSUANCE:
        raise PermissionDenied("Internal invoice issuance is disabled.")
    if reverses is not None:
        if not reverses.sealed or reverses.workspace_id != workspace.pk or reverses.kind == Journal.Kind.REVERSAL:
            raise ValidationError("Choose an original journal in your workspace.")
        if reverses.kind in INVOICE_JOURNAL_KINDS and not (invoice_correction and settings.INTERNAL_INVOICE_ISSUANCE):
            raise ValidationError("Invoice journals require the invoice correction workflow.")
        if reverses.kind in STOCK_JOURNAL_KINDS and not stock_allowed:
            raise ValidationError("Stock journals require the inventory correction workflow.")
        if date < reverses.date:
            raise ValidationError("A reversal cannot be dated before the original journal.")
        kind = Journal.Kind.REVERSAL
        branch, cost_centre = reverses.branch, reverses.cost_centre
        lines = [(line.ledger, "C" if line.side == "D" else "D", line.amount) for line in reverses.lines.all()]
    elif kind not in MANUAL_JOURNAL_KINDS + CASH_VOUCHER_KINDS + TRADE_VOUCHER_KINDS + INVOICE_JOURNAL_KINDS + STOCK_JOURNAL_KINDS:
        raise ValidationError("Choose a valid journal type.")

    if any(item and item.workspace_id != workspace.pk for item in (branch, cost_centre)):
        raise ValidationError("Choose dimensions from your workspace.")
    if not 2 <= len(lines) <= 50:
        raise ValidationError("Enter between 2 and 50 journal lines.")
    totals = {"D": Decimal(0), "C": Decimal(0)}
    fingerprint_lines = []
    for ledger, side, amount in lines:
        if ledger.workspace_id != workspace.pk or ledger.group.workspace_id != workspace.pk:
            raise ValidationError("Choose ledgers from your workspace.")
        if side not in totals or not isinstance(amount, Decimal) or not amount.is_finite() or amount <= 0:
            raise ValidationError("Each line needs a debit or credit and a positive amount.")
        DecimalValidator(15, 2)(amount)
        totals[side] += amount
        fingerprint_lines.append((ledger.pk, side, str(amount.quantize(Decimal("0.01")))))
    if totals["D"] != totals["C"]:
        raise ValidationError("Total debits and credits must be equal.")
    if kind in CASH_VOUCHER_KINDS:
        if len(lines) != 2 or lines[0][0].pk == lines[1][0].pk:
            raise ValidationError("Cash vouchers need two distinct ledgers.")
        cash_ids = set(funds_ledgers(workspace).filter(pk__in=(ledger.pk for ledger, _, _ in lines)).values_list("pk", flat=True))
        cash_sides = {side for ledger, side, _ in lines if ledger.pk in cash_ids}
        required_sides = {
            Journal.Kind.RECEIPT: {"D"}, Journal.Kind.PAYMENT: {"C"}, Journal.Kind.CONTRA: {"D", "C"},
        }
        if cash_sides != required_sides[kind]:
            raise ValidationError("The cash or bank ledger must match the voucher type.")
    if kind in TRADE_VOUCHER_KINDS:
        groups = {side: {ledger.group.kind for ledger, entry_side, _ in lines if side == entry_side} for side in ("D", "C")}
        expected = {
            Journal.Kind.SALES: ({"asset"}, {"income"}),
            Journal.Kind.PURCHASE: ({"asset", "expense"}, {"asset", "liability"}),
            Journal.Kind.DEBIT_NOTE: ({"liability"}, {"asset", "expense"}),
            Journal.Kind.CREDIT_NOTE: ({"income"}, {"asset"}),
        }[kind]
        if not groups["D"] <= expected[0] or not groups["C"] <= expected[1]:
            raise ValidationError("Choose account types that match this internal voucher.")

    payload = [date.isoformat(), kind, reference, narration, getattr(branch, "pk", None),
               getattr(cost_centre, "pk", None), getattr(reverses, "pk", None), fingerprint_lines]
    fingerprint = hashlib.sha256(json.dumps(payload).encode()).hexdigest()
    journals = Journal.objects.filter(workspace=workspace, sealed=True)
    existing = journals.filter(submission_key=submission_key).first()
    if existing:
        if existing.fingerprint != fingerprint:
            raise ValidationError("This submission key already belongs to a different journal. Start a new form.")
        return existing

    if date > timezone.localdate():
        raise ValidationError("Choose today or a past accounting date.")
    period = Period.objects.filter(year__workspace=workspace, starts_on__lte=date, ends_before__gt=date).first()
    if not period or period.locked_at:
        raise ValidationError("The accounting date needs an open period.")
    if reverses and journals.filter(reverses=reverses).exists():
        raise ValidationError("This journal has already been reversed.")
    if kind == Journal.Kind.OPENING and (journals.filter(kind=kind).exists() or journals.filter(date__lt=date).exists()):
        raise ValidationError("Post one opening journal on or before the first transaction date.")
    if journals.filter(kind=Journal.Kind.OPENING, date__gt=date).exists():
        raise ValidationError("The accounting date cannot precede the opening balances.")

    journal = Journal(workspace=workspace, period=period, date=date, kind=kind, reference=reference,
                      narration=narration, branch=branch, cost_centre=cost_centre, reverses=reverses,
                      submitted_by=actor, submission_key=submission_key, fingerprint=fingerprint)
    journal.full_clean(validate_unique=False, validate_constraints=False)
    journal.save()
    JournalLine.objects.bulk_create(JournalLine(journal=journal, ledger=ledger, side=side, amount=amount)
                                    for ledger, side, amount in lines)
    # Seal only after every line exists. The database rejects later mutations.
    journal.sealed = True
    journal.save(update_fields=["sealed"])
    return journal


@transaction.atomic
def approve_voucher(workspace, actor, draft_id, revision):
    lock_books(workspace, actor)
    draft = VoucherDraft.objects.filter(workspace=workspace, pk=draft_id).first()
    if not draft:
        raise ValidationError("Voucher is unavailable in this workspace.")
    if draft.journal_id:
        return draft.journal
    if draft.revision != revision:
        raise ValidationError("The draft changed. Review its latest allocations before approving.")
    if draft.kind not in REVIEW_VOUCHER_KINDS:
        raise ValidationError("Choose a supported voucher type.")
    ledgers = Ledger.objects.filter(workspace=workspace).in_bulk(row[0] for row in draft.allocations)
    if any(row[0] not in ledgers for row in draft.allocations):
        raise ValidationError("Every voucher ledger must belong to this workspace.")
    journal = post_journal(
        workspace, actor, date=draft.date, kind=draft.kind, reference=draft.reference,
        narration=draft.narration, submission_key=draft.posting_key,
        branch=draft.branch, cost_centre=draft.cost_centre,
        lines=[(ledgers[ledger_id], side, Decimal(amount)) for ledger_id, side, amount in draft.allocations],
    )
    draft.journal = journal
    draft.save(update_fields=["journal"])
    return journal
