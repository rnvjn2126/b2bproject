from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.test import TestCase, override_settings
from django.urls import reverse

from accounting.models import Ledger
from dashboard.models import Product
from inventory.costing import CostMethod
from inventory.purchase_costs import capitalise_purchase_cost
from inventory.sale_costs import post_sale_cost
from inventory.stock import record_stock_movement
from inventory.stock_setup import register_location, register_lot, register_warehouse
from inventory.valuation import set_valuation_method, value_stock_movement
from invoicing.issuance import cancel_internal_invoice, issue_internal_purchase, issue_internal_sale
from invoicing.returns import record_invoice_return
from invoicing.test_data import InvoiceFixture

from .reporting import financial_overview
from .trade_reports import profitability, trade_register


D = Decimal


@override_settings(INTERNAL_INVOICE_ISSUANCE=True, INTERNAL_STOCK_ACCOUNTING=True)
class TradeReportTests(InvoiceFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.dispatch.refresh_from_db()
        cls.receipt.refresh_from_db()
        cls.day = cls.receipt.date
        cls.later = cls.day + timedelta(days=1)
        line = cls.dispatch.sales_line.quote_line.rfq_line
        cls.product = Product.objects.create(owner=cls.owner, name="Synthetic report steel", shape="sheet", unit="kg")
        line.product = cls.product
        line.save(update_fields=["product"])
        warehouse = register_warehouse(cls.workspace, cls.owner, code="REPORT", name="Synthetic warehouse")
        cls.location = register_location(cls.workspace, cls.owner, warehouse_id=warehouse.pk, code="BIN", name="Bin")
        cls.lot = register_lot(cls.workspace, cls.owner, code="REPORT", product_id=cls.product.pk)

    def move(self, kind, quantity, day, order=None):
        route = {"source_id": self.location.pk} if kind == "issue" else {"destination_id": self.location.pk}
        return record_stock_movement(
            self.workspace, self.owner, lot_id=self.lot.pk, kind=kind, quantity=D(quantity), posted_on=day,
            reference="SYN-REPORT", submission_key=uuid4(), order_movement_id=getattr(order, "pk", None), **route,
        )

    def purchase_invoice(self, **overrides):
        draft = self.draft(self.receipt, purchase_unit_price=D("75"), supplier_invoice_date=self.day)
        return issue_internal_purchase(self.workspace, self.owner, **(self.purchase_issue_inputs(draft) | overrides))

    def sale_invoice(self):
        _, inputs = self.issue_inputs(self.draft(self.dispatch))
        return issue_internal_sale(self.workspace, self.owner, **inputs)

    def test_sales_return_and_profitability_use_sealed_journals_and_frozen_product(self):
        self.assertEqual(trade_register(self.workspace, "sales", self.day, self.later), [])
        buy = self.purchase_invoice()
        sale = self.sale_invoice()
        set_valuation_method(self.workspace, self.owner, method=CostMethod.FIFO)
        asset, cogs = (Ledger.objects.get(workspace=self.workspace, code=code) for code in ("1200", "5100"))
        self.move("receipt", "5", self.day, self.receipt)
        capitalise_purchase_cost(self.workspace, self.owner, invoice_id=buy.pk, inventory_ledger_id=asset.pk)
        outbound = self.move("issue", "3", self.day, self.dispatch)
        value_stock_movement(self.workspace, self.owner, movement_id=outbound.pk)
        post_sale_cost(self.workspace, self.owner, invoice_id=sale.pk, inventory_ledger_id=asset.pk,
                       expense_ledger_id=cogs.pk)
        restock = self.move("receipt", "1", self.later)
        record_invoice_return(self.workspace, self.owner, invoice_id=sale.pk, posting_on=self.later, quantity=D(1),
                              reason="Synthetic return for reporting", submission_key=uuid4(),
                              restock_movement_id=restock.pk)
        Product.objects.filter(pk=self.product.pk).update(name="Renamed after issue")
        rows = trade_register(self.workspace, "sales", self.day, self.later)
        self.assertEqual([(row.event, row.trade_amount, row.tax_posted, row.invoice_amount, row.cost) for row in rows],
                         [("Return", D(-100), D(-12), D(-112), D(-75)), ("Invoice", D(300), D(36), D(336), D(225))])
        self.assertEqual({row.product for row in rows}, {"Synthetic report steel"})
        for key in ("customer", "product"):
            group, = profitability(rows, key)
            self.assertEqual((group.revenue, group.known_cost, group.matched_gross, group.missing_cost), (200, 150, 50, 0))
        report = financial_overview(self.workspace, self.owner, self.day, self.later)
        self.assertEqual((report["sales"], report["cogs"], report["gross"]), (200, 150, 50))
        self.assertEqual(report["statements"]["difference"], 0)
        self.assertTrue(report["stock"].reconciled)

    def test_purchase_cancellation_and_scope_and_unknown_sale_cost(self):
        purchase = self.purchase_invoice()
        cancel_internal_invoice(self.workspace, self.owner, invoice_id=purchase.pk, posting_on=self.later,
                                reason="Synthetic purchase void")
        rows = trade_register(self.workspace, "purchase", self.day, self.later)
        self.assertEqual([(row.event, row.trade_amount, row.tax_posted, row.invoice_amount) for row in rows],
                         [("Cancellation", D(-375), D(-45), D(-420)), ("Invoice", D(375), D(45), D(420))])
        self.assertEqual(trade_register(self.other_workspace, "purchase", self.day, self.later), [])
        self.sale_invoice()
        group, = profitability(trade_register(self.workspace, "sales", self.day, self.later), "customer")
        self.assertEqual((group.revenue, group.missing_cost, group.matched_revenue), (300, 1, 0))

    def test_owner_can_drill_into_sealed_journal_and_foreign_cannot_read_register(self):
        sale = self.sale_invoice()
        self.client.force_login(self.owner)
        url = reverse("accounting:trade_register", args=["sales"])
        filters = {"start": self.day, "end": self.later}
        response = self.client.get(url, filters)
        self.assertContains(response, sale.number)
        self.assertContains(response, reverse("accounting:journal", args=[sale.journal_id]))
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertContains(self.client.get(reverse("accounting:finance_analysis"), filters), "Customer profitability")
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(url, filters), sale.number)
