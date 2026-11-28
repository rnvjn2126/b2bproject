import csv
from datetime import date
from decimal import Decimal
from io import BytesIO, StringIO
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from openpyxl import load_workbook

from . import test_reporting
from .models import Ledger
from .report_exports import render_report
from .report_tables import REPORT_NAMES, ReportTable


D = Decimal


class ExportSerializationTests(SimpleTestCase):
    def test_xlsx_keeps_text_literal_and_preserves_large_decimal(self):
        table = ReportTable("Synthetic", ("Name", "Amount (INR)"), [
            ("=Synthetic label", D("10.25")),
            ("Long balance", D("1234567890123456.78")),
        ])
        fixture_date = date(2026, 5, 1)
        output = render_report(table, fixture_date, fixture_date, "xlsx")
        sheet = load_workbook(BytesIO(output)).active
        self.assertEqual((sheet["A4"].data_type, sheet["A4"].value), ("s", "=Synthetic label"))
        self.assertEqual((sheet["B4"].data_type, sheet["B4"].value), ("n", 10.25))
        self.assertEqual((sheet["B5"].data_type, sheet["B5"].value), ("s", "1234567890123456.78"))
        self.assertEqual(sheet.auto_filter.ref, "A3:B5")


class FinancialExportTests(TestCase):
    post = test_reporting.FinanceDashboardTests.post

    @classmethod
    def setUpTestData(cls):
        test_reporting.FinanceDashboardTests.setUpTestData.__func__(cls)

    def download(self, report, format_name, **filters):
        url = reverse("accounting:finance_export", args=[report, format_name])
        return self.client.get(url, {"start": self.start, "end": self.end, **filters})

    def test_all_reports_export_for_owner_and_apply_date_scope(self):
        self.client.force_login(self.owner)
        for report in REPORT_NAMES:
            with self.subTest(report=report):
                response = self.download(report, "csv")
                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response.headers["Cache-Control"])
                self.assertIn("attachment;", response.headers["Content-Disposition"])
        response = self.download("trial-balance", "csv")
        totals = list(csv.reader(StringIO(response.content.decode("utf-8-sig"))))[-1]
        self.assertEqual(totals[1], "Totals")
        self.assertEqual(D(totals[-1]), D(totals[-2]))
        scoped = self.download("ledger", "csv", start=self.end, ledger=self.ledgers["1010"].pk)
        rows = list(csv.reader(StringIO(scoped.content.decode("utf-8-sig"))))
        self.assertEqual(rows[1][-2:], ["Opening", "100.00"])
        self.assertEqual(rows[-1][-2:], ["Closing", "130.00"])
        self.assertEqual(self.download("overview", "csv", start=self.end, end=self.start).status_code, 400)
        with patch.dict("accounting.report_views.ROW_LIMITS", {"csv": 1}):
            self.assertEqual(self.download("trial-balance", "csv").status_code, 400)

    def test_pdf_spreadsheet_and_csv_protect_scope_and_formula_like_text(self):
        Ledger.objects.filter(pk=self.ledgers["4000"].pk).update(name="   =Synthetic only")
        self.client.force_login(self.owner)
        exported = self.download("profit-loss", "csv")
        self.assertIn("'   =Synthetic only", exported.content.decode("utf-8-sig"))
        exported = self.download("profit-loss", "xlsx")
        sheet = load_workbook(BytesIO(exported.content)).active
        self.assertEqual((sheet["C4"].data_type, sheet["C4"].value), ("s", "   =Synthetic only"))
        doc = self.download("profit-loss", "pdf")
        self.assertTrue(doc.content.startswith(b"%PDF-"))
        foreign_ledger = Ledger.objects.get(workspace=self.foreign, code="1000")
        self.assertEqual(self.download("ledger", "xlsx", ledger=foreign_ledger.pk).status_code, 404)
        self.client.force_login(self.member)
        for format_name in ("pdf", "xlsx", "csv"):
            self.assertEqual(self.download("overview", format_name).status_code, 403)
