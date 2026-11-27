from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounting.models import Journal

from . import test_movements
from .costing import CostMethod
from .models import ValuationEvent, ValuationLayer
from .stock import record_stock_movement
from .stock_setup import register_lot
from .valuation import set_valuation_method, value_stock_movement


D = Decimal


class ValuationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        test_movements.StockMovementTests.setUpTestData.__func__(cls)
        cls.later_lot = register_lot(cls.workspace, cls.owner, code="LOT-2", product_id=cls.product.pk)
        cls.day = date(2026, 5, 1)

    def move(self, kind, quantity, **overrides):
        fields = dict(lot_id=self.lot.pk, kind=kind, quantity=D(quantity), posted_on=self.day,
                      reference="SYN-COST", submission_key=uuid4())
        return record_stock_movement(self.workspace, self.owner, **(fields | overrides))

    def value(self, movement, **costs):
        return value_stock_movement(self.workspace, self.owner, movement_id=movement.pk, **costs)

    def set_method(self, method):
        return set_valuation_method(self.workspace, self.owner, method=method)

    def test_fifo_pools_locations_and_keeps_receipt_components(self):
        self.set_method(CostMethod.FIFO)
        first = self.move("receipt", "5", destination_id=self.a.pk)
        second = self.move("receipt", "8", lot_id=self.later_lot.pk, destination_id=self.a.pk)
        transfer = self.move("transfer", "6", lot_id=self.later_lot.pk, source_id=self.a.pk, destination_id=self.b.pk)
        dispatch = self.move("issue", "6", lot_id=self.later_lot.pk, source_id=self.b.pk)
        valued = self.value(first, material=D("50"), freight=D("7.50"), packaging=D("2.50"))
        self.assertEqual((valued.amount, valued.freight, valued.packaging), (60, D("7.50"), D("2.50")))
        self.value(second, material=D("128"))
        shifted = self.value(transfer)
        self.assertEqual((shifted.amount, shifted.closing_quantity, shifted.closing_amount), (0, 13, 188))
        issue = self.value(dispatch)
        self.assertEqual((issue.amount, issue.closing_quantity, issue.closing_amount), (76, 7, 112))
        self.assertEqual(list(ValuationLayer.objects.order_by("receipt_id").values_list("quantity", "amount")),
                         [(0, 0), (7, 112)])
        self.assertFalse(Journal.objects.exists())

    def test_moving_average_reflects_receipts_and_partial_issue(self):
        self.set_method(CostMethod.AVERAGE)
        one = self.move("receipt", "4", destination_id=self.a.pk)
        two = self.move("receipt", "6", lot_id=self.later_lot.pk, destination_id=self.b.pk)
        self.value(one, material=D("40"))
        self.value(two, material=D("90"))
        issue = self.value(self.move("issue", "3", lot_id=self.later_lot.pk, source_id=self.b.pk))
        self.assertEqual((issue.amount, issue.closing_quantity, issue.closing_amount), (39, 7, 91))
        self.assertFalse(ValuationLayer.objects.exists())

    def test_policy_order_and_idempotent_cost_recording(self):
        one = self.move("receipt", "5", destination_id=self.a.pk)
        two = self.move("receipt", "5", destination_id=self.a.pk)
        with self.assertRaisesMessage(ValidationError, "valuation method first"):
            self.value(one, material=D("50"))
        self.set_method(CostMethod.AVERAGE)
        self.set_method(CostMethod.FIFO)
        with self.assertRaisesMessage(ValidationError, "earlier stock movements"):
            self.value(two, material=D("50"))
        with self.assertRaisesMessage(ValidationError, "material cost explicitly"):
            self.value(one)
        first = self.value(one, material=D("50"))
        self.assertEqual(self.value(one, material=D("50")), first)
        with self.assertRaisesMessage(ValidationError, "already been valued"):
            self.value(one, material=D("60"))
        with self.assertRaisesMessage(ValidationError, "formal transition"):
            self.set_method(CostMethod.AVERAGE)
        self.assertEqual(ValuationEvent.objects.count(), 1)

    def test_prevents_backdated_stock_across_lots_and_foreign_access(self):
        self.set_method(CostMethod.FIFO)
        later_day = self.day + timedelta(days=1)
        posted = self.move("receipt", "5", destination_id=self.a.pk, posted_on=later_day)
        with self.assertRaises(PermissionDenied):
            value_stock_movement(self.workspace, self.other, movement_id=posted.pk, material=D("50"))
        with self.assertRaisesMessage(ValidationError, "movement in this company"):
            value_stock_movement(self.foreign, self.other, movement_id=posted.pk, material=D("50"))
        self.value(posted, material=D("50"))
        with self.assertRaisesMessage(ValidationError, "precedes an existing valuation"):
            self.move("receipt", "5", lot_id=self.later_lot.pk, destination_id=self.b.pk)

    def test_valuation_rows_are_immutable_and_fifo_persists_atomically(self):
        self.set_method(CostMethod.FIFO)
        receipt = self.move("receipt", "5", destination_id=self.a.pk)
        valued = self.value(receipt, material=D("50"))
        issue = self.move("issue", "3", source_id=self.a.pk)
        with self.assertRaisesMessage(IntegrityError, "immutable"), transaction.atomic():
            ValuationEvent.objects.filter(pk=valued.pk).update(amount=D("99"))
        with patch("inventory.valuation.ValuationEvent.objects.create", side_effect=IntegrityError):
            with self.assertRaises(IntegrityError):
                self.value(issue)
        layer = ValuationLayer.objects.get(receipt=valued)
        self.assertEqual((layer.quantity, layer.amount), (5, 50))
        self.assertEqual(ValuationEvent.objects.count(), 1)
        valued_issue = self.value(issue)
        self.assertEqual(valued_issue.closing_amount, 20)
        with self.assertRaisesMessage(IntegrityError, "immutable"), transaction.atomic():
            valued_issue.delete()
