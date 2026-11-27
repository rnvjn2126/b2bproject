from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounting.models import Journal, Ledger

from . import tests as banking_tests
from .models import FundsAccount, ReportedInstrument


@override_settings(INTERNAL_INVOICE_ISSUANCE=True)
class BankingOperationsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        banking_tests.BankingTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.client.force_login(self.owner)

    def test_owner_registers_account_and_transfers_to_its_book(self):
        ledger = Ledger.objects.create(workspace=self.workspace, code="1050", name="Reserve cash",
                                       group=self.cash_ledger.group)
        accounts = reverse("accounting:bank_accounts")
        self.assertContains(self.client.get(accounts), "Register funds account")
        response = self.client.post(accounts, {"ledger": ledger.pk, "name": "Reserve cash", "kind": "cash"})
        reserve = FundsAccount.objects.get(ledger=ledger)
        book = reverse("accounting:bank_book", args=[reserve.pk])
        self.assertRedirects(response, book)
        day = date(2026, 5, 1)
        transfer = reverse("accounting:bank_transfer")
        params = {"from_account": self.bank.pk, "to_account": reserve.pk, "amount": "40.25", "posting_on": day,
                  "submission_key": uuid4(), "reference": "Synthetic transfer"}
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.owner)
        self.assertEqual(strict.post(transfer, params).status_code, 403)
        self.assertEqual(self.client.post(transfer, params).status_code, 302)
        self.assertEqual(self.client.post(transfer, params).status_code, 302)
        self.assertEqual(Journal.objects.get().kind, Journal.Kind.CONTRA)
        report = self.client.get(book, {"start_on": day, "end_on": day})
        self.assertContains(report, "Closing INR 40.25")
        self.assertIn("no-store", report.headers["Cache-Control"])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(book).status_code, 404)

    def test_cheque_reporting_records_history_without_changing_the_book(self):
        instrument_url = reverse("accounting:bank_instrument", args=[self.bank.pk])
        day = date(2026, 5, 1)
        response = self.client.post(instrument_url, {
            "method": "cheque", "direction": "in", "reference": "SYN CHEQUE", "amount": "100.50", "reported_on": day,
        })
        self.assertEqual(response.status_code, 302)
        item = ReportedInstrument.objects.get()
        action = reverse("accounting:bank_cheque", args=[item.pk])
        with self.settings(INTERNAL_INVOICE_ISSUANCE=False):
            self.assertEqual(self.client.get(action).status_code, 404)
        event = {"state": "presented", "happened_on": day, "submission_key": uuid4()}
        self.assertRedirects(self.client.post(action, event), action)
        self.assertContains(self.client.get(action), "Reported presented")
        self.assertEqual(item.amount, Decimal("100.50"))
        self.assertFalse(Journal.objects.exists())
