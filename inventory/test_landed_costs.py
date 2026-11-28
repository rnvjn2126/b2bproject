from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from accounting.models import Journal, Ledger
from accounting.services import post_journal, setup_books
from dashboard.models import Product
from invoicing.issuance import issue_internal_purchase
from invoicing.test_data import InvoiceFixture
from orders.models import OrderMovement

from .costing import CostMethod
from .landed_costs import allocate_purchase_charge
from .models import LandedCharge
from .purchase_costs import capitalise_purchase_cost
from .reconciliation import reconcile_stock_to_ledger
from .stock import record_stock_movement
from .stock_setup import register_location, register_lot, register_warehouse
from .valuation import set_valuation_method, value_stock_movement


D = Decimal


@override_settings(INTERNAL_INVOICE_ISSUANCE=True, INTERNAL_STOCK_ACCOUNTING=True)
class LandedChargeTests(InvoiceFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.receipt.refresh_from_db()
        cls.day = cls.receipt.date
        cls.charge_day = cls.day + timedelta(days=1)
        cls.second = OrderMovement.objects.create(purchase_order=cls.receipt.purchase_order, quantity=D(2),
                                                  date=cls.day, reference="SYN-R2", recorded_by=cls.owner)
        line = cls.receipt.purchase_order.requirement.quote_line.rfq_line
        product = Product.objects.create(owner=cls.owner, name="Synthetic freight steel", shape="sheet", unit="kg")
        line.product = product
        line.save(update_fields=["product"])
        warehouse = register_warehouse(cls.workspace, cls.owner, code="LAND", name="Synthetic warehouse")
        cls.location = register_location(cls.workspace, cls.owner, warehouse_id=warehouse.pk, code="BIN", name="Bin")
        cls.lot = register_lot(cls.workspace, cls.owner, code="LAND", product_id=product.pk)
        setup_books(cls.workspace, cls.owner, 2026)
        cls.asset = Ledger.objects.get(workspace=cls.workspace, code="1200")
        cls.expense = Ledger.objects.get(workspace=cls.workspace, code="5100")
        cls.cash = Ledger.objects.get(workspace=cls.workspace, code="1000")

    def movement(self, kind, quantity, day, *, linked=None):
        route = {"source_id": self.location.pk} if kind == "issue" else {"destination_id": self.location.pk}
        return record_stock_movement(
            self.workspace, self.owner, lot_id=self.lot.pk, kind=kind, quantity=D(quantity), posted_on=day,
            reference="SYN-LANDED-STOCK", submission_key=uuid4(), order_movement_id=getattr(linked, "pk", None), **route,
        )

    def purchases(self, method):
        set_valuation_method(self.workspace, self.owner, method=method)
        costs = []
        for movement, price, reference in ((self.receipt, "75", "SYN-FIRST"), (self.second, "125", "SYN-SECOND")):
            draft = self.draft(movement, purchase_unit_price=D(price), supplier_invoice_date=self.day)
            values = self.purchase_issue_inputs(draft) | {"supplier_reference": reference}
            invoice = issue_internal_purchase(self.workspace, self.owner, **values)
            self.movement("receipt", movement.quantity, self.day, linked=movement)
            costs.append(capitalise_purchase_cost(self.workspace, self.owner, invoice_id=invoice.pk,
                                                 inventory_ledger_id=self.asset.pk))
        return costs

    def charge_line(self, amount):
        entry = post_journal(
            self.workspace, self.owner, date=self.charge_day, kind=Journal.Kind.GENERAL, reference="SYN-FREIGHT",
            narration="Synthetic separately posted freight or packaging", submission_key=uuid4(),
            lines=[(self.expense, "D", D(amount)), (self.cash, "C", D(amount))],
        )
        return entry.lines.get(side="D")

    def allocate(self, source, purchases, **overrides):
        defaults = dict(source_line_id=source.pk, purchase_ids=[item.pk for item in purchases],
                        kind="freight", posted_on=self.charge_day)
        return allocate_purchase_charge(self.workspace, self.owner, **(defaults | overrides))

    def report(self, day):
        return reconcile_stock_to_ledger(self.workspace, self.owner, ledger_id=self.asset.pk, as_of=day)

    def test_fifo_charge_preserves_historical_values_and_increases_open_cost_layers(self):
        first, second = self.purchases(CostMethod.FIFO)
        source = self.charge_line("50")
        charge = self.allocate(source, [first, second])
        self.assertEqual(self.allocate(source, [second, first]), charge)
        self.assertEqual(list(charge.allocations.order_by("purchase_id").values_list("amount", flat=True)),
                         [D(30), D(20)])
        self.assertEqual(list(charge.journal.lines.values_list("side", "amount")), [("D", D(50)), ("C", D(50))])
        self.assertEqual(self.report(self.day).inventory_value, D(625))
        self.assertTrue(self.report(self.day).reconciled)
        self.assertEqual(self.report(self.charge_day).inventory_value, D(675))
        self.assertTrue(self.report(self.charge_day).reconciled)
        with self.assertRaisesMessage(ValidationError, "or landed charge"):
            self.movement("issue", "1", self.day)
        later = self.charge_day + timedelta(days=1)
        issue = self.movement("issue", "6", later)
        valued = value_stock_movement(self.workspace, self.owner, movement_id=issue.pk)
        self.assertEqual((valued.amount, valued.closing_amount), (D(540), D(135)))
        self.assertEqual((self.report(later).inventory_value, self.report(later).difference), (D(135), D(-540)))
        first.receipt.refresh_from_db()
        self.assertEqual(first.receipt.amount, D(375))
        with self.assertRaisesMessage(IntegrityError, "immutable"), transaction.atomic():
            LandedCharge.objects.filter(pk=charge.pk).update(kind="packaging")
        with self.assertRaisesMessage(ValidationError, "requires an inventory correction"):
            post_journal(self.workspace, self.owner, date=self.charge_day, kind=Journal.Kind.REVERSAL,
                         reference="SYN-INVALID", narration="Synthetic reversal guard", submission_key=uuid4(),
                         reverses=source.journal)

    def test_weighted_average_includes_multiple_anchored_charges_once(self):
        costs = self.purchases(CostMethod.AVERAGE)
        self.allocate(self.charge_line("50"), costs)
        self.allocate(self.charge_line("10"), costs, kind="packaging")
        self.assertEqual(self.report(self.charge_day).inventory_value, D("685.00"))
        issue = self.movement("issue", "2", self.charge_day)
        first = value_stock_movement(self.workspace, self.owner, movement_id=issue.pk)
        self.assertEqual((first.amount, first.closing_amount), (D("195.71"), D("489.29")))
        issue = self.movement("issue", "5", self.charge_day)
        second = value_stock_movement(self.workspace, self.owner, movement_id=issue.pk)
        self.assertEqual((second.amount, second.closing_amount), (D("489.29"), D("0.00")))

    def test_consumed_stock_and_scope_require_review_without_posting(self):
        first, second = self.purchases(CostMethod.FIFO)
        issue = self.movement("issue", "1", self.day)
        value_stock_movement(self.workspace, self.owner, movement_id=issue.pk)
        source = self.charge_line("25")
        with self.assertRaisesMessage(ValidationError, "already consumed"):
            self.allocate(source, [first, second])
        with self.assertRaises(PermissionDenied):
            allocate_purchase_charge(self.workspace, self.other, source_line_id=source.pk, purchase_ids=[first.pk],
                                     kind="freight", posted_on=self.charge_day)
        with self.assertRaisesMessage(ValidationError, "sealed freight"):
            allocate_purchase_charge(self.other_workspace, self.other, source_line_id=source.pk,
                                     purchase_ids=[second.pk], kind="freight", posted_on=self.charge_day)
        self.assertFalse(LandedCharge.objects.exists())

    @override_settings(INTERNAL_INVENTORY=True)
    def test_owner_cost_allocation_form_and_history(self):
        costs = self.purchases(CostMethod.FIFO)
        source = self.charge_line("60")
        action = reverse("accounting:inventory:action", args=["landed-charge"])
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(action), "Allocate freight or packaging")
        self.assertRedirects(self.client.post(action, {
            "source_line_id": source.pk, "purchase_ids": [cost.pk for cost in costs],
            "kind": "packaging", "posted_on": self.charge_day.isoformat(),
        }), reverse("accounting:inventory:overview"))
        review = self.client.get(reverse("accounting:inventory:valuation_review"))
        self.assertContains(review, "Recent landed charges")
        self.assertContains(review, "INR 60.00")
