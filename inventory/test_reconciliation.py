from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from accounting.models import Journal, Ledger
from accounting.services import post_journal, setup_books

from . import test_movements
from .costing import CostMethod
from .reconciliation import reconcile_stock_to_ledger
from .stock import record_stock_movement
from .valuation import set_valuation_method, value_stock_movement


class StockReconciliationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        test_movements.StockMovementTests.setUpTestData.__func__(cls)
        setup_books(cls.workspace, cls.owner, 2026)
        setup_books(cls.foreign, cls.other, 2026)
        cls.ledger = Ledger.objects.get(workspace=cls.workspace, code="1200")
        cls.expense = Ledger.objects.get(workspace=cls.workspace, code="5000")
        cls.day = date(2026, 5, 1)
        set_valuation_method(cls.workspace, cls.owner, method=CostMethod.FIFO)

    def movement(self, kind, quantity, day, **route):
        return record_stock_movement(
            self.workspace, self.owner, lot_id=self.lot.pk, kind=kind, quantity=Decimal(quantity),
            posted_on=day, reference="SYN-RECONCILE", submission_key=uuid4(), **route,
        )

    def posting(self, day, side, amount):
        return post_journal(
            self.workspace, self.owner, date=day, kind=Journal.Kind.GENERAL, reference="SYN-GL",
            narration="Synthetic reconciliation control balance", submission_key=uuid4(),
            lines=[(self.ledger, side, Decimal(amount)), (self.expense, "C" if side == "D" else "D", Decimal(amount))],
        )

    def report(self, day=None, **overrides):
        fields = {"ledger_id": self.ledger.pk, "as_of": day or self.day}
        return reconcile_stock_to_ledger(self.workspace, self.owner, **(fields | overrides))

    def test_dated_stock_quantity_and_sealed_ledger_tie_out(self):
        inbound = self.movement("receipt", "10", self.day, destination_id=self.a.pk)
        self.posting(self.day, "D", "100.03")
        unvalued = self.report()
        self.assertEqual((unvalued.ledger_balance, unvalued.inventory_value, unvalued.difference), (Decimal("100.03"), 0, Decimal("-100.03")))
        self.assertEqual((unvalued.pools[0].quantity_gap, unvalued.unvalued_movements), (10, 1))
        self.assertFalse(unvalued.reconciled)

        value_stock_movement(self.workspace, self.owner, movement_id=inbound.pk, material=Decimal("100.03"))
        self.assertTrue(self.report().reconciled)
        later = self.day + timedelta(days=1)
        outbound = self.movement("issue", "4", later, source_id=self.a.pk)
        value_stock_movement(self.workspace, self.owner, movement_id=outbound.pk)
        self.assertEqual(self.report(later).difference, Decimal("-40.01"))
        self.posting(later, "C", "40.01")
        result = self.report(later)
        self.assertTrue(result.reconciled)
        self.assertEqual((result.pools[0].on_hand, result.inventory_value), (6, Decimal("60.02")))
        self.assertEqual(self.report().inventory_value, Decimal("100.03"))
        self.assertTrue(self.report(self.day - timedelta(days=1)).reconciled)

    def test_unvalued_zero_value_activity_still_requires_review(self):
        self.movement("receipt", "1", self.day, destination_id=self.a.pk)
        result = self.report()
        self.assertEqual(result.difference, 0)
        self.assertFalse(result.reconciled)
        self.assertEqual(result.unvalued_movements, 1)

    def test_scope_and_asset_classification(self):
        with self.assertRaises(PermissionDenied):
            reconcile_stock_to_ledger(self.workspace, self.other, ledger_id=self.ledger.pk, as_of=self.day)
        foreign = Ledger.objects.get(workspace=self.foreign, code="1200")
        for ledger in (foreign, self.expense):
            with self.subTest(ledger=ledger), self.assertRaisesMessage(ValidationError, "asset ledger"):
                self.report(ledger_id=ledger.pk)

    @override_settings(INTERNAL_INVENTORY=True)
    def test_owner_records_receipt_cost_and_reviews_the_ledger(self):
        inbound = self.movement("receipt", "5", self.day, destination_id=self.a.pk)
        self.client.force_login(self.owner)
        url = reverse("accounting:inventory:valuation_review")
        values = {"ledger_id": self.ledger.pk, "as_of": self.day.isoformat()}
        self.assertContains(self.client.get(url, values), "Review unvalued movements")
        action = reverse("accounting:inventory:action", args=["value-movement"])
        self.assertContains(self.client.get(action), "SYN-RECONCILE")
        self.assertRedirects(self.client.post(action, {
            "movement_id": inbound.pk, "material": "77.33", "freight": "22.67", "packaging": "0", "other": "0",
        }), reverse("accounting:inventory:overview"))
        self.assertFalse(Journal.objects.exists())
        self.posting(self.day, "D", "100")
        report = self.client.get(url, values)
        self.assertContains(report, "Stock quantities and ledger value agree for this date.")
        self.assertContains(report, "INR 100.00")
        self.assertIn("no-store", report.headers["Cache-Control"])
        self.client.force_login(self.other)
        self.assertContains(self.client.get(url, values), "Select a valid choice.")
        self.assertNotContains(self.client.get(url, values), "Sample sheet")
