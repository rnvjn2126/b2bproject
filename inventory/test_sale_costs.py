from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from accounting.models import Journal, Ledger
from accounting.services import lock_period, post_journal
from dashboard.models import Product
from invoicing.issuance import cancel_internal_invoice, issue_internal_sale
from invoicing.returns import record_invoice_return
from invoicing.test_data import InvoiceFixture

from .costing import CostMethod
from .models import SaleCost, SaleCostCorrection, ValuationEvent
from .reconciliation import reconcile_stock_to_ledger
from .sale_costs import post_sale_cost
from .stock import record_stock_movement
from .stock_setup import register_location, register_lot, register_warehouse
from .valuation import set_valuation_method, value_stock_movement


D = Decimal


@override_settings(INTERNAL_INVOICE_ISSUANCE=True, INTERNAL_STOCK_ACCOUNTING=True)
class SaleCostTests(InvoiceFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.receipt.refresh_from_db()
        cls.dispatch.refresh_from_db()
        line = cls.dispatch.sales_line.quote_line.rfq_line
        product = Product.objects.create(owner=cls.owner, name="Synthetic kg inventory", shape="sheet", unit="kg")
        line.product = product
        line.save(update_fields=["product"])
        warehouse = register_warehouse(cls.workspace, cls.owner, code="COST", name="Synthetic warehouse")
        cls.location = register_location(cls.workspace, cls.owner, warehouse_id=warehouse.pk, code="BIN", name="Bin")
        cls.lot = register_lot(cls.workspace, cls.owner, code="COST", product_id=product.pk)
        set_valuation_method(cls.workspace, cls.owner, method=CostMethod.FIFO)
        fixture = cls()
        fixture.draft_sale = fixture.draft(cls.dispatch)
        cls.year, invoice_data = fixture.issue_inputs(fixture.draft_sale)
        cls.invoice = issue_internal_sale(cls.workspace, cls.owner, **invoice_data)
        cls.asset = Ledger.objects.get(workspace=cls.workspace, code="1200")
        cls.expense = Ledger.objects.get(workspace=cls.workspace, code="5100")
        cls.offset = Ledger.objects.get(workspace=cls.workspace, code="5000")
        cls.day = cls.dispatch.date

    def move(self, kind, quantity, *, linked=None, when=None):
        route = {"source_id": self.location.pk} if kind == "issue" else {"destination_id": self.location.pk}
        return record_stock_movement(
            self.workspace, self.owner, lot_id=self.lot.pk, kind=kind, quantity=D(quantity), posted_on=when or self.day,
            reference="SYN-COST", submission_key=uuid4(), order_movement_id=getattr(linked, "pk", None), **route,
        )

    def value_dispatch(self, *, price="400.00"):
        receipt = self.move("receipt", "5", linked=self.receipt)
        value_stock_movement(self.workspace, self.owner, movement_id=receipt.pk, material=D(price))
        dispatch = self.move("issue", "3", linked=self.dispatch)
        return value_stock_movement(self.workspace, self.owner, movement_id=dispatch.pk)

    def put_cost_in_asset(self, amount="400.00"):
        post_journal(
            self.workspace, self.owner, date=self.day, kind=Journal.Kind.GENERAL, reference="SYN-ACQUISITION",
            narration="Synthetic inventory acquisition balance", submission_key=uuid4(),
            lines=[(self.asset, "D", D(amount)), (self.offset, "C", D(amount))],
        )

    def post_cost(self, **overrides):
        args = dict(invoice_id=self.invoice.pk, inventory_ledger_id=self.asset.pk, expense_ledger_id=self.expense.pk)
        return post_sale_cost(self.workspace, self.owner, **(args | overrides))

    def check_balance(self, day, expected):
        review = reconcile_stock_to_ledger(self.workspace, self.owner, ledger_id=self.asset.pk, as_of=day)
        self.assertTrue(review.reconciled)
        self.assertEqual(review.inventory_value, D(expected))

    def test_cost_posts_only_with_exact_dispatch_and_reviewed_asset_cost(self):
        with self.assertRaisesMessage(ValidationError, "linked to this dispatch"):
            self.post_cost()
        dispatch = self.value_dispatch()
        with self.assertRaisesMessage(ValidationError, "reviewed acquisition"):
            self.post_cost()
        self.put_cost_in_asset()
        cost = self.post_cost()
        self.assertEqual(cost.issue, dispatch)
        self.assertEqual(cost.journal.kind, Journal.Kind.STOCK_COST)
        self.assertEqual(cost.journal.date, self.invoice.posting_on)
        self.assertTrue(cost.journal.sealed)
        self.assertEqual(list(cost.journal.lines.values_list("side", "ledger_id", "amount")),
                         [("D", self.expense.pk, D("240")), ("C", self.asset.pk, D("240"))])
        self.assertEqual(self.post_cost(), cost)
        with self.assertRaisesMessage(ValidationError, "different ledgers"):
            self.post_cost(expense_ledger_id=self.offset.pk)
        with self.assertRaisesMessage(ValidationError, "inventory correction"):
            post_journal(self.workspace, self.owner, date=self.day, kind=Journal.Kind.REVERSAL,
                         reference="SYN-INVALID", narration="Synthetic unauthorized reversal",
                         submission_key=uuid4(), reverses=cost.journal)
        with self.assertRaisesMessage(IntegrityError, "immutable"), transaction.atomic():
            SaleCost.objects.filter(pk=cost.pk).update(expense_ledger=self.offset)
        self.check_balance(self.day, "160")

    def test_partial_returns_restore_historical_cost_with_cumulative_rounding(self):
        self.value_dispatch(price="500.05")
        self.put_cost_in_asset("500.05")
        original = self.post_cost()
        day = self.day + timedelta(days=1)
        receipts = [self.move("receipt", "1", when=day), self.move("receipt", "2", when=day)]
        args = dict(invoice_id=self.invoice.pk, posting_on=day, quantity=D(1), reason="Synthetic physical return",
                    submission_key=uuid4(), restock_movement_id=receipts[0].pk)
        first = record_invoice_return(self.workspace, self.owner, **args)
        self.assertEqual(record_invoice_return(self.workspace, self.owner, **args), first)
        self.assertEqual(first.salecostcorrection.receipt.amount, D("100.01"))
        wrong = args | {"quantity": D(2), "submission_key": uuid4()}
        with self.assertRaisesMessage(ValidationError, "unvalued restock receipt"):
            record_invoice_return(self.workspace, self.owner, **wrong)
        self.assertEqual(self.invoice.returns.count(), 1)
        second = record_invoice_return(self.workspace, self.owner, **(wrong | {"restock_movement_id": receipts[1].pk}))
        self.assertEqual(second.salecostcorrection.receipt.amount, D("200.02"))
        self.assertEqual(original.corrections.count(), 2)
        self.check_balance(day, "500.05")

    def test_cancellation_requires_restock_and_reverses_cost_and_invoice_atomically(self):
        self.value_dispatch()
        self.put_cost_in_asset()
        cost = self.post_cost()
        day = self.day + timedelta(days=1)
        args = dict(invoice_id=self.invoice.pk, posting_on=day, reason="Synthetic cancellation")
        with self.assertRaisesMessage(ValidationError, "confirmed stock receipt"):
            cancel_internal_invoice(self.workspace, self.owner, **args)
        self.assertFalse(Journal.objects.filter(reverses=self.invoice.journal).exists())
        self.assertFalse(SaleCostCorrection.objects.exists())
        receipt = self.move("receipt", "3", when=day)
        with self.assertRaises(PermissionDenied):
            with self.settings(INTERNAL_STOCK_ACCOUNTING=False):
                cancel_internal_invoice(self.workspace, self.owner, **args, restock_movement_id=receipt.pk)
        self.assertFalse(ValuationEvent.objects.filter(movement=receipt).exists())
        cancellation = cancel_internal_invoice(self.workspace, self.owner, **args, restock_movement_id=receipt.pk)
        self.assertEqual(cancellation.salecostcorrection.journal.reverses_id, cost.journal_id)
        self.assertEqual(cancellation.reversal.reverses_id, self.invoice.journal_id)
        self.assertEqual(cancel_internal_invoice(self.workspace, self.owner, **args,
                                                 restock_movement_id=receipt.pk), cancellation)
        self.check_balance(day, "400.00")

    def test_zero_cost_requires_open_period_and_creates_no_empty_journal(self):
        self.value_dispatch(price="0")
        cost = self.post_cost()
        self.assertIsNone(cost.journal)
        self.assertFalse(Journal.objects.filter(kind=Journal.Kind.STOCK_COST).exists())
        self.check_balance(self.day, "0")

    def test_permissions_and_locked_period_are_enforced(self):
        self.value_dispatch()
        self.put_cost_in_asset()
        with self.settings(INTERNAL_STOCK_ACCOUNTING=False), self.assertRaises(PermissionDenied):
            self.post_cost()
        with self.assertRaises(PermissionDenied):
            post_sale_cost(self.workspace, self.other, invoice_id=self.invoice.pk,
                           inventory_ledger_id=self.asset.pk, expense_ledger_id=self.expense.pk)
        with self.assertRaisesMessage(ValidationError, "in this company"):
            post_sale_cost(self.other_workspace, self.other, invoice_id=self.invoice.pk,
                           inventory_ledger_id=self.asset.pk, expense_ledger_id=self.expense.pk)
        period = self.year.periods.get(starts_on=self.day)
        lock_period(self.workspace, self.owner, period.pk)
        with self.assertRaisesMessage(ValidationError, "open period"):
            self.post_cost()
        self.assertFalse(SaleCost.objects.exists())
