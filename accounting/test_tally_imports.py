from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from dashboard.models import BusinessAccount, Customer, Product, Supplier

from .models import AccountGroup, Journal, Ledger, TallyImportBatch, TallyImportRecord
from .services import setup_books
from .tally_imports import run_tally_import
from .tally_xml import parse_tally_xml


def envelope(records):
    return f"<ENVELOPE><BODY><DATA><TALLYMESSAGE>{records}</TALLYMESSAGE></DATA></BODY></ENVELOPE>".encode()


def voucher(kind, number, debit, credit, amount):
    def entry(name, side, value):
        return (f"<ALLLEDGERENTRIES.LIST><LEDGERNAME>{name}</LEDGERNAME><ISDEEMEDPOSITIVE>{side}</ISDEEMEDPOSITIVE>"
                f"<AMOUNT>{value}</AMOUNT></ALLLEDGERENTRIES.LIST>")
    return (f"<VOUCHER><DATE>20260502</DATE><GUID>SYN-{number}</GUID><VOUCHERTYPENAME>{kind}</VOUCHERTYPENAME>"
            f"<VOUCHERNUMBER>{number}</VOUCHERNUMBER>{entry(debit, 'Yes', -amount)}"
            f"{entry(credit, 'No', amount)}</VOUCHER>")


MASTERS = """
<GROUP NAME="Synthetic Customer Group"><PARENT>Sundry Debtors</PARENT></GROUP>
<LEDGER NAME="Synthetic buyer"><PARENT>Synthetic Customer Group</PARENT><EMAIL>buyer@example.test</EMAIL></LEDGER>
<LEDGER NAME="Synthetic vendor"><PARENT>Sundry Creditors</PARENT></LEDGER>
<LEDGER NAME="Cash"><PARENT>Cash-in-Hand</PARENT><OPENINGBALANCE>-1000</OPENINGBALANCE></LEDGER>
<LEDGER NAME="Capital"><PARENT>Capital Account</PARENT><OPENINGBALANCE>1000</OPENINGBALANCE></LEDGER>
<STOCKITEM NAME="Synthetic plate"><BASEUNITS>KG</BASEUNITS></STOCKITEM>
"""
VOUCHERS = (
    voucher("Sales", "1", "Synthetic buyer", "Steel sales", 200)
    + voucher("Purchase", "2", "Steel purchases", "Synthetic vendor", 80)
    + voucher("Receipt", "3", "Cash", "Synthetic buyer", 200)
    + voucher("Payment", "4", "Synthetic vendor", "Cash", 80)
)


class TallyImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.owner = users.create_user(username="synthetic-tally")
        cls.other = users.create_user(username="separate-tally")
        cls.workspace = BusinessAccount.objects.create(owner=cls.owner, name="Synthetic Tally workspace")
        cls.foreign = BusinessAccount.objects.create(owner=cls.other, name="Synthetic other workspace")
        setup_books(cls.workspace, cls.owner, 2026)
        setup_books(cls.foreign, cls.other, 2026)
        cls.opening = date(2026, 5, 1)

    def run_document(self, document, **options):
        return run_tally_import(self.workspace, self.owner, document, opening_on=self.opening, **options)

    def test_dry_run_atomic_commit_opening_and_overlapping_vouchers(self):
        data = envelope(MASTERS + VOUCHERS)
        preview = self.run_document(data)
        self.assertEqual((preview.created, preview.opening_debit, preview.opening_credit), (10, 1000, 1000))
        self.assertFalse(TallyImportBatch.objects.exists())
        self.assertFalse(Customer.objects.exists())
        self.assertFalse(Journal.objects.exists())
        batch = self.run_document(data, confirmed_key=preview.key)
        self.assertEqual(self.run_document(data, confirmed_key=preview.key), batch)
        self.assertTrue(self.run_document(data).previously_committed)
        overlap = envelope(MASTERS + "\n" + VOUCHERS)
        separate = self.run_document(overlap)
        self.assertEqual((separate.created, separate.reused), (0, 10))
        self.run_document(overlap, confirmed_key=separate.key)
        self.assertEqual(TallyImportRecord.objects.count(), 10)
        self.assertEqual(Journal.objects.count(), 5)
        self.assertTrue(Journal.objects.filter(kind="opening", sealed=True, pk=batch.opening_journal_id).exists())
        self.assertEqual(Customer.objects.get(owner=self.owner).email, "buyer@example.test")
        self.assertEqual(Supplier.objects.get(owner=self.owner).name, "Synthetic vendor")
        self.assertEqual(Product.objects.get(owner=self.owner).unit, "kg")
        for journal in Journal.objects.all():
            amounts = {"D": Decimal(0), "C": Decimal(0)}
            for line in journal.lines.all():
                amounts[line.side] += line.amount
            self.assertEqual(amounts["D"], amounts["C"])

    def test_rejects_unbalanced_opening_and_missing_voucher_without_partial_changes(self):
        bad = envelope(MASTERS.replace(">1000</OPENINGBALANCE>", ">900</OPENINGBALANCE>"))
        with self.assertRaisesMessage(ValidationError, "Opening balances are unbalanced"):
            self.run_document(bad)
        bad = envelope(MASTERS + voucher("Sales", "NEW", "Missing", "Steel sales", 200))
        with self.assertRaisesMessage(ValidationError, "Import or map voucher ledger"):
            self.run_document(bad)
        self.assertFalse(Customer.objects.exists())
        self.assertFalse(Product.objects.exists())
        self.assertFalse(Journal.objects.exists())
        self.assertFalse(TallyImportBatch.objects.exists())

    def test_owner_scope_different_payload_and_conflicting_identity(self):
        data = envelope(MASTERS + VOUCHERS)
        with self.assertRaises(PermissionDenied):
            run_tally_import(self.workspace, self.other, data, opening_on=self.opening)
        preview = self.run_document(data)
        with self.assertRaisesMessage(ValidationError, "Run a new preview"):
            self.run_document(data, mapping={"ledgers": {"Cash": "1000"}}, confirmed_key=preview.key)
        self.run_document(data, confirmed_key=preview.key)
        modified = envelope(voucher("Sales", "1", "Synthetic buyer", "Steel sales", 210))
        with self.assertRaisesMessage(ValidationError, "different data"):
            self.run_document(modified)
        self.assertEqual(Journal.objects.filter(workspace=self.workspace).count(), 5)
        self.assertFalse(Journal.objects.filter(workspace=self.foreign).exists())

    def test_explicit_existing_ledger_mapping_is_scoped(self):
        group = AccountGroup.objects.get(workspace=self.workspace, code="INCOME-1")
        other_income = Ledger.objects.create(workspace=self.workspace, group=group, code="TARGET", name="Synthetic revenue map")
        data = envelope(MASTERS + voucher("Sales", "1", "Synthetic buyer", "Tally Ledger", 200))
        mappings = {"ledgers": {"Tally Ledger": other_income.code}}
        preview = self.run_document(data, mapping=mappings)
        self.run_document(data, mapping=mappings, confirmed_key=preview.key)
        self.assertTrue(Journal.objects.get(kind="sales").lines.filter(ledger=other_income, side="C").exists())
        with self.assertRaisesMessage(ValidationError, "existing ledger code"):
            self.run_document(envelope(voucher("Sales", "2", "Synthetic buyer", "Tally Ledger", 200)),
                              mapping={"ledgers": {"Tally Ledger": "NOT-FOUND"}})

    def test_parser_rejects_dtds_destructive_actions_and_unsupported_scope(self):
        dtd = b"<!DOCTYPE ENVELOPE>" + envelope(MASTERS)
        with self.assertRaisesMessage(ValidationError, "well-formed XML"):
            parse_tally_xml(dtd)
        with self.assertRaisesMessage(ValidationError, "Only create"):
            parse_tally_xml(envelope('<LEDGER NAME="Cash" Action="Delete"><PARENT>Cash-in-Hand</PARENT></LEDGER>'))
        with self.assertRaisesMessage(ValidationError, "catalogue-only"):
            parse_tally_xml(envelope('<STOCKITEM NAME="Synthetic"><BASEUNITS>kg</BASEUNITS><OPENINGBALANCE>5 kg</OPENINGBALANCE></STOCKITEM>'))
        with self.assertRaisesMessage(ValidationError, "equal total debits and credits"):
            parse_tally_xml(envelope(voucher("Sales", "3", "Cash", "Steel sales", 200).replace(">200</AMOUNT>", ">100</AMOUNT>")))
