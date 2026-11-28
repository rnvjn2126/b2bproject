from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from accounting.models import Journal, Ledger
from accounting.services import setup_books
from dashboard.models import Product
from invoicing.issuance import cancel_internal_invoice, issue_internal_purchase
from invoicing.returns import record_invoice_return
from invoicing.test_data import InvoiceFixture

from .costing import CostMethod
from .models import PurchaseCost, ValuationEvent
from .purchase_costs import capitalise_purchase_cost
from .reconciliation import reconcile_stock_to_ledger
from .stock import record_stock_movement
from .stock_setup import register_location, register_lot, register_warehouse
from .valuation import set_valuation_method, value_stock_movement


D = Decimal


@override_settings(INTERNAL_INVOICE_ISSUANCE=True, INTERNAL_STOCK_ACCOUNTING=True)
class PurchaseCostTests(InvoiceFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.receipt.refresh_from_db()
        requirement = cls.receipt.purchase_order.requirement.quote_line.rfq_line
        product = Product.objects.create(owner=cls.owner, name="Synthetic purchase", shape="sheet", unit="kg")
        requirement.product = product
        requirement.save(update_fields=["product"])
        warehouse = register_warehouse(cls.workspace, cls.owner, code="ACQ", name="Synthetic warehouse")
        cls.location = register_location(cls.workspace, cls.owner, warehouse_id=warehouse.pk, code="BIN", name="Bin")
        cls.lot = register_lot(cls.workspace, cls.owner, code="ACQ", product_id=product.pk)
        cls.day = cls.receipt.date
        setup_books(cls.workspace, cls.owner, 2026)
        cls.asset = Ledger.objects.get(workspace=cls.workspace, code="1200")
        set_valuation_method(cls.workspace, cls.owner, method=CostMethod.AVERAGE)

    def invoice(self, *, direct=False):
        draft = self.draft(self.receipt, purchase_unit_price=D("75"), supplier_invoice_date=self.day)
        values = self.purchase_issue_inputs(draft)
        if direct:
            values["ledger_ids"]["purchases"] = self.asset.pk
        return issue_internal_purchase(self.workspace, self.owner, **values)

    def move(self, kind, quantity, *, linked=False, when=None):
        route = {"source_id": self.location.pk} if kind == "issue" else {"destination_id": self.location.pk}
        return record_stock_movement(
            self.workspace, self.owner, lot_id=self.lot.pk, kind=kind, quantity=D(quantity), posted_on=when or self.day,
            reference="SYN-ACQUISITION", submission_key=uuid4(), order_movement_id=self.receipt.pk if linked else None,
            **route,
        )

    def capitalise(self, invoice):
        return capitalise_purchase_cost(self.workspace, self.owner, invoice_id=invoice.pk, inventory_ledger_id=self.asset.pk)

    def check_balance(self, day, expected):
        review = reconcile_stock_to_ledger(self.workspace, self.owner, ledger_id=self.asset.pk, as_of=day)
        self.assertTrue(review.reconciled)
        self.assertEqual(review.inventory_value, D(expected))

    def test_links_exact_receipt_and_moves_only_sealed_acquisition_debit(self):
        invoice = self.invoice()
        with self.assertRaisesMessage(ValidationError, "exact stock receipt"):
            self.capitalise(invoice)
        movement = self.move("receipt", "5", linked=True)
        record = self.capitalise(invoice)
        self.assertEqual(record.receipt.movement, movement)
        self.assertEqual(record.receipt.amount, D("375.00"))
        self.assertEqual(invoice.total, D("420.00"))
        self.assertEqual(record.journal.kind, Journal.Kind.STOCK_ACQUISITION)
        self.assertEqual(list(record.journal.lines.values_list("side", "ledger_id", "amount")),
                         [("D", self.asset.pk, D("375")), ("C", record.source_line.ledger_id, D("375"))])
        self.assertEqual(self.capitalise(invoice), record)
        with self.assertRaisesMessage(IntegrityError, "immutable"), transaction.atomic():
            PurchaseCost.objects.filter(pk=record.pk).update(recorded_by=self.other)
        self.check_balance(self.day, "375.00")

    def test_direct_asset_purchase_and_partial_return_avoid_duplicate_postings(self):
        invoice = self.invoice(direct=True)
        self.move("receipt", "5", linked=True)
        cost = self.capitalise(invoice)
        self.assertIsNone(cost.journal_id)
        day = self.day + timedelta(days=1)
        outbound = self.move("issue", "2", when=day)
        data = dict(invoice_id=invoice.pk, posting_on=day, quantity=D(2), reason="Synthetic supplier return",
                    submission_key=uuid4(), restock_movement_id=outbound.pk)
        result = record_invoice_return(self.workspace, self.owner, **data)
        self.assertEqual(record_invoice_return(self.workspace, self.owner, **data), result)
        self.assertIsNone(result.purchasecostcorrection.journal_id)
        self.assertEqual(result.purchasecostcorrection.issue.amount, D(150))
        self.check_balance(day, "225")

    def test_cancel_reverses_acquisition_with_matching_stock_issue(self):
        invoice = self.invoice()
        self.move("receipt", "5", linked=True)
        cost = self.capitalise(invoice)
        day = self.day + timedelta(days=1)
        data = dict(invoice_id=invoice.pk, posting_on=day, reason="Synthetic supplier cancellation")
        with self.assertRaisesMessage(ValidationError, "confirmed stock return issue"):
            cancel_internal_invoice(self.workspace, self.owner, **data)
        self.assertFalse(Journal.objects.filter(reverses=invoice.journal).exists())
        outbound = self.move("issue", "5", when=day)
        cancellation = cancel_internal_invoice(self.workspace, self.owner, restock_movement_id=outbound.pk, **data)
        self.assertEqual(cancellation.purchasecostcorrection.journal.reverses_id, cost.journal_id)
        self.check_balance(day, "0")

    def test_cost_variance_and_unverified_extra_costs_do_not_change_the_ledger(self):
        invoice = self.invoice()
        self.move("receipt", "5", linked=True)
        self.capitalise(invoice)
        other = self.move("receipt", "5")
        value_stock_movement(self.workspace, self.owner, movement_id=other.pk, material=D("425"))
        day = self.day + timedelta(days=1)
        outbound = self.move("issue", "2", when=day)
        with self.assertRaisesMessage(ValidationError, "cost variance"):
            record_invoice_return(self.workspace, self.owner, invoice_id=invoice.pk, posting_on=day, quantity=D(2),
                                  reason="Synthetic variance", submission_key=uuid4(), restock_movement_id=outbound.pk)
        self.assertFalse(invoice.returns.exists())
        self.assertFalse(ValuationEvent.objects.filter(movement=outbound).exists())

    def test_scope_and_gate(self):
        invoice = self.invoice()
        self.move("receipt", "5", linked=True)
        with self.settings(INTERNAL_STOCK_ACCOUNTING=False), self.assertRaises(PermissionDenied):
            self.capitalise(invoice)
        with self.assertRaises(PermissionDenied):
            capitalise_purchase_cost(self.workspace, self.other, invoice_id=invoice.pk, inventory_ledger_id=self.asset.pk)
        with self.assertRaisesMessage(ValidationError, "issued purchase invoice"):
            capitalise_purchase_cost(self.other_workspace, self.other, invoice_id=invoice.pk,
                                     inventory_ledger_id=self.asset.pk)
        self.assertFalse(PurchaseCost.objects.exists())

    @override_settings(INTERNAL_INVENTORY=True)
    def test_owner_acquisition_and_cancellation_screens_require_stock_evidence(self):
        invoice = self.invoice()
        self.move("receipt", "5", linked=True)
        review = reverse("accounting:inventory:valuation_review")
        action = reverse("accounting:inventory:action", args=["purchase-cost"])
        self.client.force_login(self.owner)
        with self.settings(INTERNAL_STOCK_ACCOUNTING=False):
            self.assertEqual(self.client.get(action).status_code, 404)
            self.assertNotContains(self.client.get(review), "Capitalise a purchase")
        self.assertContains(self.client.get(review), "Capitalise a purchase")
        self.assertRedirects(self.client.post(action, {"invoice_id": invoice.pk, "inventory_ledger_id": self.asset.pk}),
                             reverse("accounting:inventory:overview"))
        cancel = reverse("accounting:invoice_cancel", args=[invoice.pk])
        day = self.day + timedelta(days=1)
        issue = self.move("issue", "5", when=day)
        self.assertContains(self.client.get(cancel), "Confirmed stock movement")
        values = {"posting_on": day.isoformat(), "reason": "Synthetic supplier cancellation"}
        self.assertContains(self.client.post(cancel, values), "This field is required.")
        self.assertRedirects(self.client.post(cancel, values | {"restock_movement_id": issue.pk}),
                             reverse("accounting:invoice_print", args=[invoice.pk]))
        self.check_balance(day, "0")
