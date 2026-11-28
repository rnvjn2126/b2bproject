from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook

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

    def test_excel_fields_map_into_the_same_atomic_posting_pipeline(self):
        file = BytesIO()
        book = Workbook()
        ledgers = book.active
        ledgers.title = "Ledgers"
        ledgers.append(["Ledger label", "Parent", "Opening Balance"])
        ledgers.append(["Cash", "Cash-in-Hand", "-1000.00"])
        ledgers.append(["Capital", "Capital Account", "1000.00"])
        items = book.create_sheet("Stock Items")
        items.append(["Name", "Base Units"])
        items.append(["Synthetic workbook plate", "kg"])
        vouchers = book.create_sheet("Vouchers")
        vouchers.append(["Voucher Type", "Date", "Voucher Number", "Ledger Name", "Debit", "Credit"])
        vouchers.append(["Receipt", date(2026, 5, 2), "WB-1", "Cash", 25, None])
        vouchers.append(["Receipt", date(2026, 5, 2), "WB-1", "Steel sales", None, 25])
        book.save(file)
        options = {"mapping": {"columns": {"ledgers": {"name": "Ledger label"}}}, "source_format": "xlsx"}
        check = self.run_document(file.getvalue(), **options)
        sheet_batch = self.run_document(file.getvalue(), confirmed_key=check.key, **options)
        self.assertEqual(sheet_batch.source_format, "xlsx")
        self.assertEqual((sheet_batch.opening_amount, sheet_batch.created_count), (1000, 4))
        self.assertEqual(Journal.objects.count(), 2)
        self.assertTrue(Product.objects.filter(name="Synthetic workbook plate").exists())

    def test_excel_formula_and_duplicate_column_mapping_are_rejected(self):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Stock Items"
        worksheet.append(["Name", "Base Units"])
        worksheet.append(["=SyntheticItem", "kg"])
        file = BytesIO()
        workbook.save(file)
        with self.assertRaisesMessage(ValidationError, "Formulas"):
            self.run_document(file.getvalue(), source_format="xlsx")
        with self.assertRaisesMessage(ValidationError, "one destination field"):
            self.run_document(file.getvalue(), source_format="xlsx",
                              mapping={"columns": {"stock items": {"unit": "Name"}}})
        self.assertFalse(Product.objects.exists())

    @override_settings(INTERNAL_TALLY_IMPORT=True)
    def test_owner_preview_confirmation_history_and_export_preserve_scope(self):
        url = reverse("accounting:tally_migration")
        private = Client(enforce_csrf_checks=True)
        private.force_login(self.owner)
        response = private.get(url)
        self.assertContains(response, "Tally migration")
        upload = envelope(MASTERS + VOUCHERS)
        payload = {"opening_on": self.opening.isoformat(), "source": SimpleUploadedFile("synthetic.xml", upload)}
        self.assertEqual(private.post(url, payload).status_code, 403)
        payload["source"] = SimpleUploadedFile("synthetic.xml", upload)
        payload["csrfmiddlewaretoken"] = private.cookies["csrftoken"].value
        response = private.post(url, payload)
        self.assertContains(response, "Commit validated import")
        token = response.context["confirmation"].initial["preview_token"]
        self.assertFalse(TallyImportBatch.objects.exists())
        confirmation = {
            "action": "confirm", "confirm-opening_on": self.opening.isoformat(),
            "confirm-preview_token": token, "confirm-source": SimpleUploadedFile("synthetic.xml", upload),
            "csrfmiddlewaretoken": payload["csrfmiddlewaretoken"],
        }
        private.force_login(self.other)
        confirmation["csrfmiddlewaretoken"] = private.cookies["csrftoken"].value
        self.assertContains(private.post(url, confirmation), "Run a new import preview")
        private.force_login(self.owner)
        confirmation["csrfmiddlewaretoken"] = private.cookies["csrftoken"].value
        confirmation["confirm-source"] = SimpleUploadedFile("synthetic.xml", upload)
        self.assertRedirects(private.post(url, confirmation), url)
        self.assertContains(private.get(url), "10 new")
        exported = private.get(reverse("accounting:tally_export"), {"start": self.opening, "end": date(2026, 5, 2)})
        self.assertEqual(exported.status_code, 200)
        self.assertIn("no-store", exported.headers["Cache-Control"])
        self.assertEqual(len(parse_tally_xml(exported.content)), 4)
        replay = self.run_document(exported.content)
        self.run_document(exported.content, confirmed_key=replay.key)
        self.assertEqual(Journal.objects.count(), 5)
        other_preview = run_tally_import(self.foreign, self.other, envelope(MASTERS), opening_on=self.opening)
        run_tally_import(self.foreign, self.other, envelope(MASTERS), opening_on=self.opening, confirmed_key=other_preview.key)
        other_vouchers = run_tally_import(self.foreign, self.other, exported.content)
        run_tally_import(self.foreign, self.other, exported.content, confirmed_key=other_vouchers.key)
        self.assertEqual(Journal.objects.filter(workspace=self.foreign, sealed=True).count(), 5)
        with self.settings(INTERNAL_TALLY_IMPORT=False):
            self.assertEqual(private.get(url).status_code, 404)
