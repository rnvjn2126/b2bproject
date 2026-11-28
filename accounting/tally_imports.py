import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from django.core.exceptions import ValidationError
from django.db import transaction

from banking.services import register_funds_account
from dashboard.models import Customer, Product, Supplier

from .models import AccountGroup, Journal, Ledger, TallyImportBatch, TallyImportRecord
from .services import lock_books, post_journal
from .tally_xml import GroupRow, LedgerRow, StockRow, VoucherRow, parse_tally_xml


STARTER_GROUPS = {
    "assets": "ASSET", "current assets": "ASSET-1", "fixed assets": "ASSET-2", "sundry debtors": "ASSET-3",
    "bank accounts": "ASSET-4", "cash-in-hand": "ASSET-5", "cash accounts": "ASSET-5", "stock-in-hand": "ASSET-1",
    "liabilities": "LIABILITY", "current liabilities": "LIABILITY-1", "secured loans": "LIABILITY-2",
    "unsecured loans": "LIABILITY-3", "sundry creditors": "LIABILITY-4", "duties & taxes": "LIABILITY-5",
    "duties and taxes": "LIABILITY-5", "capital account": "EQUITY-1", "reserves & surplus": "EQUITY-2",
    "sales accounts": "INCOME-1", "direct incomes": "INCOME-2", "indirect incomes": "INCOME-3",
    "purchase accounts": "EXPENSE-1", "direct expenses": "EXPENSE-2", "indirect expenses": "EXPENSE-3",
}
ZERO = Decimal("0.00")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def normalise_mapping(mapping):
    if mapping is None:
        return {}
    if not isinstance(mapping, dict) or set(mapping) - {"groups", "ledgers"}:
        raise ValidationError("Use a mapping with groups and ledgers.")
    result = {}
    for category, source in mapping.items():
        if not isinstance(source, dict) or len(source) > 500:
            raise ValidationError("Each mapping must map source names to existing account codes.")
        converted = {}
        for name, target in source.items():
            if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 120
                    or not isinstance(target, str) or not 1 <= len(target.strip()) <= 24):
                raise ValidationError("Map a named source account to an existing account code.")
            key = name.strip().casefold()
            if key in converted:
                raise ValidationError("A source name can have only one mapping.")
            converted[key] = target.strip()
        result[category] = converted
    return result


@dataclass(frozen=True)
class ImportPreview:
    key: str
    created: int
    reused: int
    opening_debit: Decimal
    opening_credit: Decimal
    rows: tuple
    previously_committed: bool = False


class ImportPlan:
    def __init__(self, workspace, actor, mapping):
        self.workspace = workspace
        self.actor = actor
        self.groups = {row.code: row for row in AccountGroup.objects.filter(workspace=workspace)}
        self.ledgers = {row.code: row for row in Ledger.objects.filter(
            workspace=workspace, group__workspace=workspace,
        ).select_related("group")}
        self.group_targets = STARTER_GROUPS | mapping.get("groups", {})
        self.ledger_targets = mapping.get("ledgers", {})
        self.existing = {(row.kind, row.identity): row for row in TallyImportRecord.objects.filter(workspace=workspace)}
        self.pending = []
        self.rows = []
        self.file_keys = set()
        self.reused = 0

    def record(self, kind, name, inputs, create):
        key = kind, fingerprint(name.casefold())
        if key in self.file_keys:
            raise ValidationError(f"Duplicate {kind} identity in this file: {name}.")
        self.file_keys.add(key)
        content = fingerprint(inputs)
        existing = self.existing.get(key)
        if existing:
            if existing.fingerprint != content:
                raise ValidationError(f"Previously imported {kind} has different data: {name}.")
            self.reused += 1
            self.rows.append((kind, name, "Already recorded"))
            return existing.target_id
        target = create()
        self.pending.append(TallyImportRecord(workspace=self.workspace, kind=kind, identity=key[1],
                                              fingerprint=content, target_id=target.pk))
        self.rows.append((kind, name, str(target)))
        return target.pk

    def group_named(self, name):
        key = name.casefold()
        code = self.group_targets.get(key)
        if code:
            if code not in self.groups:
                raise ValidationError(f"Group mapping for {name} requires account group {code}. Set up the chart first.")
            return self.groups[code]
        code = "TG-" + fingerprint(key)[:16].upper()
        return self.groups.get(code)

    def import_groups(self, rows):
        pending = list(rows)
        while pending:
            unresolved = []
            for row in pending:
                mapped = self.group_targets.get(row.name.casefold())
                parent = None if mapped else self.group_named(row.parent)
                if not mapped and parent is None:
                    unresolved.append(row)
                    continue
                code = mapped or "TG-" + fingerprint(row.name.casefold())[:16].upper()

                def create():
                    if mapped:
                        return self.group_named(row.name)
                    group, _ = AccountGroup.objects.get_or_create(
                        workspace=self.workspace, code=code,
                        defaults={"name": row.name, "parent": parent, "kind": parent.kind},
                    )
                    if group.parent_id != parent.pk or group.kind != parent.kind or group.name != row.name:
                        raise ValidationError(f"Account group differs from the source: {row.name}.")
                    self.groups[code] = group
                    return group

                self.record("group", row.name, (row.name, row.parent, code), create)
                self.group_named(row.name)
            if len(unresolved) == len(pending):
                raise ValidationError(f"Map or import the missing parent group: {unresolved[0].parent}.")
            pending = unresolved

    def ledger_named(self, name):
        key = name.casefold()
        code = self.ledger_targets.get(key)
        if code:
            ledger = self.ledgers.get(code)
            if ledger is None:
                raise ValidationError(f"Map {name} to an existing ledger code.")
            return ledger
        known = self.existing.get(("ledger", fingerprint(key)))
        if known:
            return next((ledger for ledger in self.ledgers.values() if ledger.pk == known.target_id), None)
        candidates = [ledger for ledger in self.ledgers.values() if ledger.name.casefold() == key]
        if len(candidates) > 1:
            raise ValidationError(f"Map the ambiguous ledger name: {name}.")
        return candidates[0] if candidates else None

    def ancestry(self, group):
        by_id = {row.pk: row for row in self.groups.values()}
        codes = set()
        while group and group.code not in codes:
            codes.add(group.code)
            group = by_id.get(group.parent_id)
        return codes

    def import_ledger(self, row):
        group = self.group_named(row.parent)
        if group is None:
            raise ValidationError(f"Map or import the ledger parent: {row.parent}.")
        actual = self.ledger_named(row.name)

        def create():
            ledger = actual or Ledger.objects.create(
                workspace=self.workspace, code="TL-" + fingerprint(row.name.casefold())[:16].upper(),
                name=row.name, group=group,
            )
            self.ledgers[ledger.code] = ledger
            return ledger

        if actual and actual.group_id != group.pk:
            raise ValidationError(f"Ledger mapping disagrees with the source group: {row.name}.")
        pk = self.record("ledger", row.name, (row.name, group.code, row.email, row.phone, row.address), create)
        if actual and actual.pk != pk:
            raise ValidationError(f"This source ledger already has a different mapping: {row.name}.")
        ledger = next((ledger for ledger in self.ledgers.values() if ledger.pk == pk), None)
        if ledger is None:
            raise ValidationError(f"The imported ledger is no longer available: {row.name}.")
        self.ledger_targets[row.name.casefold()] = ledger.code
        groups = self.ancestry(group)
        contacts = Customer if "ASSET-3" in groups else Supplier if "LIABILITY-4" in groups else None
        if contacts:
            address_field = "billing_address" if contacts is Customer else "address"
            contacts.objects.get_or_create(owner=self.actor, name=row.name, defaults={
                "email": row.email, "phone": row.phone, address_field: row.address,
            })
        if ledger.code not in ("1000", "1010") and not hasattr(ledger, "funds_account"):
            if "ASSET-4" in groups or "ASSET-5" in groups:
                register_funds_account(self.workspace, self.actor, ledger_id=ledger.pk, name=ledger.name,
                                       kind="bank" if "ASSET-4" in groups else "cash")
        return ledger

    def import_stock(self, row):
        def create():
            product, _ = Product.objects.get_or_create(owner=self.actor, name=row.name,
                                                       defaults={"unit": row.unit, "shape": Product.Shape.OTHER})
            if product.unit != row.unit:
                raise ValidationError(f"Existing catalogue unit differs: {row.name}.")
            return product
        pk = self.record("stock", row.name, (row.name, row.unit), create)
        if not Product.objects.filter(owner=self.actor, pk=pk).exists():
            raise ValidationError(f"The imported product is no longer available: {row.name}.")

    def import_voucher(self, row):
        lines = []
        for name, amount in row.lines:
            ledger = self.ledger_named(name)
            if ledger is None:
                raise ValidationError(f"Import or map voucher ledger: {name}.")
            lines.append((ledger, "D" if amount < 0 else "C", abs(amount)))
        lines.sort(key=lambda line: (line[0].pk, line[1], line[2]))

        def create():
            return post_journal(
                self.workspace, self.actor, date=row.date, kind=row.kind, reference=f"Tally {row.kind} {row.number}",
                narration=row.narration, submission_key=uuid5(NAMESPACE_URL, f"tally/{self.workspace.pk}/{row.key.casefold()}"),
                lines=lines,
            )
        self.record("voucher", row.key, (
            row.kind, row.date, row.number, row.narration, [(ledger.pk, side, amount) for ledger, side, amount in lines],
        ), create)


@transaction.atomic
def run_tally_import(workspace, actor, content, *, opening_on=None, mapping=None, confirmed_key=None):
    lock_books(workspace, actor)
    mapping = normalise_mapping(mapping)
    if opening_on is not None and type(opening_on) is not date:
        raise ValidationError("Choose a valid opening date.")
    source_format = "xml"
    rows = parse_tally_xml(content)
    raw = hashlib.sha256(content).hexdigest()
    key = fingerprint([source_format, raw, mapping, opening_on])
    if confirmed_key is not None and confirmed_key != key:
        raise ValidationError("The file, dates or mapping changed. Run a new preview.")
    prior = TallyImportBatch.objects.filter(workspace=workspace, execution_key=key).first()
    if prior:
        if confirmed_key is not None:
            return prior
        return ImportPreview(key, prior.created_count, prior.reused_count, prior.opening_amount, prior.opening_amount, (), True)

    plan = ImportPlan(workspace, actor, mapping)
    plan.import_groups(row for row in rows if isinstance(row, GroupRow))
    opening = {}
    for row in rows:
        if isinstance(row, LedgerRow):
            ledger = plan.import_ledger(row)
            if ledger in opening:
                raise ValidationError("Map each source ledger to a distinct target when importing its opening balance.")
            opening[ledger] = row.opening
        if isinstance(row, StockRow):
            plan.import_stock(row)
    debit = sum((-value for value in opening.values() if value < 0), ZERO)
    credit = sum((value for value in opening.values() if value > 0), ZERO)
    if debit != credit:
        raise ValidationError(f"Opening balances are unbalanced. Debits {debit:.2f}, credits {credit:.2f}.")
    opening_journal = None
    if debit:
        if opening_on is None:
            raise ValidationError("Choose an opening date for the nonzero ledger balances.")
        lines = [(ledger, "D" if value < 0 else "C", abs(value))
                 for ledger, value in sorted(opening.items(), key=lambda item: item[0].pk) if value]
        opening_journal = post_journal(
            workspace, actor, date=opening_on, kind=Journal.Kind.OPENING, reference="Tally opening balances",
            narration="Verified opening balances imported from Tally",
            submission_key=uuid5(NAMESPACE_URL, f"tally/{workspace.pk}/opening/{opening_on}"), lines=lines,
        )
    for row in sorted((row for row in rows if isinstance(row, VoucherRow)), key=lambda row: (row.date, row.key)):
        plan.import_voucher(row)
    if confirmed_key is None:
        transaction.set_rollback(True)
        return ImportPreview(key, len(plan.pending), plan.reused, debit, credit, tuple(plan.rows))
    batch = TallyImportBatch.objects.create(
        workspace=workspace, actor=actor, file_digest=raw, execution_key=key, created_count=len(plan.pending),
        reused_count=plan.reused, source_format=source_format, opening_journal=opening_journal, opening_amount=debit,
    )
    for record in plan.pending:
        record.batch = batch
    TallyImportRecord.objects.bulk_create(plan.pending)
    return batch
