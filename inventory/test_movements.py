from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounting.models import Journal
from dashboard.models import Product
from invoicing.test_data import InvoiceFixture

from . import tests as geometry_tests
from .models import StockMovement, StockPosition
from .services import save_specification
from .stock import record_stock_movement
from .stock_setup import register_location, register_lot, register_warehouse


class StockMovementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        geometry_tests.SteelCatalogueTests.setUpTestData.__func__(cls)
        save_specification(cls.workspace, cls.owner, product_id=cls.product.pk, profile="sheet", grade="SYN",
                           density_kg_m3=Decimal("7850"), length_mm=Decimal("2000"), width_mm=Decimal("1000"),
                           thickness_mm=Decimal("2"))
        cls.lot = register_lot(cls.workspace, cls.owner, code="LOT-1", product_id=cls.product.pk)
        warehouse = register_warehouse(cls.workspace, cls.owner, code="STOCK", name="Synthetic stock")
        other = register_warehouse(cls.workspace, cls.owner, code="OUTLET", name="Synthetic outlet")
        foreign = register_warehouse(cls.foreign, cls.other, code="STOCK", name="Foreign stock")
        cls.a = register_location(cls.workspace, cls.owner, warehouse_id=warehouse.pk, code="BIN", name="Bin")
        cls.b = register_location(cls.workspace, cls.owner, warehouse_id=other.pk, code="BIN", name="Bin")
        cls.c = register_location(cls.foreign, cls.other, warehouse_id=foreign.pk, code="BIN", name="Foreign bin")

    def move(self, kind, quantity, **values):
        defaults = {"lot_id": self.lot.pk, "kind": kind, "quantity": Decimal(quantity), "posted_on": date(2026, 5, 1),
                    "reference": "SYN-STOCK", "submission_key": uuid4()}
        return record_stock_movement(self.workspace, self.owner, **(defaults | values))

    def balances(self):
        return dict(StockPosition.objects.filter(lot=self.lot).values_list("location_id", "on_hand"))

    def test_receipt_transfer_and_issue_preserve_mass_and_balances(self):
        receipt = self.move("receipt", "10", destination_id=self.a.pk, actual_kg=Decimal("316.123"))
        self.assertEqual((receipt.actual_kg, receipt.theoretical_kg), (Decimal("316.123"), Decimal("314")))
        transfer = self.move("transfer", "4", source_id=self.a.pk, destination_id=self.b.pk)
        retry = self.move("transfer", "4", source_id=self.a.pk, destination_id=self.b.pk,
                          submission_key=transfer.submission_key)
        self.assertEqual(retry, transfer)
        with self.assertRaisesMessage(ValidationError, "different stock movement"):
            self.move("transfer", "3", source_id=self.a.pk, destination_id=self.b.pk,
                      submission_key=transfer.submission_key)
        self.move("issue", "2", source_id=self.b.pk)
        self.assertEqual(self.balances(), {self.a.pk: Decimal("6"), self.b.pk: Decimal("2")})
        with self.assertRaises(IntegrityError), transaction.atomic():
            StockMovement.objects.filter(pk=receipt.pk).update(quantity=Decimal("1"))
        self.assertEqual(StockMovement.objects.count(), 3)
        self.assertFalse(Journal.objects.exists())

    def test_stock_rejects_overselling_and_cross_company_locations(self):
        self.move("receipt", "3", destination_id=self.a.pk)
        with self.assertRaisesMessage(ValidationError, "exceed available stock"):
            self.move("issue", "4", source_id=self.a.pk)
        with self.assertRaisesMessage(ValidationError, "locations in this company"):
            self.move("transfer", "1", source_id=self.a.pk, destination_id=self.c.pk)
        with self.assertRaises(ValidationError):
            self.move("issue", "0.5", source_id=self.a.pk)
        self.assertEqual(self.balances(), {self.a.pk: Decimal("3")})
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_stock_balances_roll_back_when_a_movement_cannot_be_saved(self):
        self.move("receipt", "3", destination_id=self.a.pk)
        with patch("inventory.stock.StockMovement.objects.create", side_effect=IntegrityError):
            with self.assertRaises(IntegrityError):
                self.move("transfer", "2", source_id=self.a.pk, destination_id=self.b.pk)
        self.assertEqual(self.balances(), {self.a.pk: Decimal("3")})
        self.assertEqual(StockMovement.objects.count(), 1)


class OrderStockTests(InvoiceFixture, TestCase):
    def test_real_receipt_and_dispatch_models_link_to_stock_once(self):
        self.receipt.refresh_from_db()
        self.dispatch.refresh_from_db()
        requirement = self.dispatch.sales_line.quote_line.rfq_line
        product = Product.objects.create(owner=self.owner, name="Synthetic stock item", shape="other",
                                         unit=self.dispatch.sales_line.unit)
        requirement.product = product
        requirement.save(update_fields=["product"])
        warehouse = register_warehouse(self.workspace, self.owner, code="SYN", name="Synthetic site")
        location = register_location(self.workspace, self.owner, warehouse_id=warehouse.pk, code="BIN", name="Bin")
        lot = register_lot(self.workspace, self.owner, code="SYN", product_id=product.pk)

        def post(source, kind, **route):
            return record_stock_movement(self.workspace, self.owner, lot_id=lot.pk, kind=kind, posted_on=source.date,
                                         quantity=source.quantity, order_movement_id=source.pk,
                                         submission_key=uuid4(), reference=source.reference, **route)

        post(self.receipt, "receipt", destination_id=location.pk)
        post(self.dispatch, "issue", source_id=location.pk)
        with self.assertRaisesMessage(ValidationError, "already been recorded"):
            post(self.receipt, "receipt", destination_id=location.pk)
        self.assertEqual(StockPosition.objects.get(lot=lot, location=location).on_hand,
                         self.receipt.quantity - self.dispatch.quantity)
        self.assertFalse(Journal.objects.exists())
