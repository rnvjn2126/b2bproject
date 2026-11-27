from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from accounting.models import Journal

from . import test_reservations
from .counts import record_physical_count
from .models import StockCount, StockMovement
from .reports import reorder_status, set_reorder_policy, stock_ageing
from .reservations import reserve_stock
from .stock import record_stock_movement
from .stock_setup import register_lot


class StockReviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        test_reservations.ReservationTests.setUpTestData.__func__(cls)

    def count(self, value, **overrides):
        fields = dict(lot_id=self.lot.pk, location_id=self.a.pk, counted=Decimal(value),
                      posted_on=self.day + timedelta(days=1), reference="SYN-COUNT", submission_key=uuid4())
        return record_physical_count(self.workspace, self.owner, **(fields | overrides))

    def test_count_keeps_unchanged_and_adjusted_evidence_and_replays(self):
        unchanged = self.count("10")
        self.assertIsNone(unchanged.adjustment_id)
        with self.assertRaisesMessage(ValidationError, "chronological"):
            record_stock_movement(self.workspace, self.owner, lot_id=self.lot.pk, kind="issue",
                                  quantity=Decimal(1), source_id=self.a.pk, posted_on=self.day,
                                  reference="OLD", submission_key=uuid4())
        reduction = self.count("6")
        self.assertEqual((reduction.before, reduction.counted), (10, 6))
        self.assertEqual((reduction.adjustment.kind, reduction.adjustment.quantity), ("issue", 4))
        self.assertEqual(self.count("6", submission_key=reduction.submission_key), reduction)
        with self.assertRaisesMessage(ValidationError, "different physical count"):
            self.count("5", submission_key=reduction.submission_key)
        increase = self.count("8")
        self.assertEqual((increase.adjustment.kind, increase.adjustment.quantity), ("receipt", 2))
        self.position.refresh_from_db()
        self.assertEqual(self.position.on_hand, 8)
        self.assertEqual(StockCount.objects.count(), 3)
        self.assertFalse(Journal.objects.exists())

    def test_count_scope_reservations_and_atomic_rollback(self):
        reserve_stock(self.workspace, self.owner, position_id=self.position.pk, quantity=Decimal(8),
                      posted_on=self.day, reference="SYN-HOLD", submission_key=uuid4())
        with self.assertRaisesMessage(ValidationError, "below reserved stock"):
            self.count("7")
        with self.assertRaisesMessage(ValidationError, "in this company"):
            self.count("10", location_id=self.c.pk)
        with self.assertRaisesMessage(ValidationError, "whole number"):
            self.count("8.5")
        with patch("inventory.counts.StockCount.objects.create", side_effect=IntegrityError):
            with self.assertRaises(IntegrityError):
                self.count("9")
        self.position.refresh_from_db()
        self.assertEqual((self.position.on_hand, self.position.reserved), (10, 8))
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertFalse(StockCount.objects.exists())

    def test_reorder_uses_unreserved_quantities_and_flags_unit_changes(self):
        set_reorder_policy(self.workspace, self.owner, product_id=self.product.pk, warehouse_id=self.a.warehouse_id,
                           minimum_available=Decimal(3))
        self.assertFalse(reorder_status(self.workspace)[0].needs_reorder)
        reserve_stock(self.workspace, self.owner, position_id=self.position.pk, quantity=Decimal(7),
                      posted_on=self.day, reference="SYN-HOLD", submission_key=uuid4())
        current = reorder_status(self.workspace)[0]
        self.assertEqual(current.available, 3)
        self.assertTrue(current.needs_reorder)
        self.assertEqual(reorder_status(self.foreign), [])
        self.product.unit = "kg"
        self.product.save(update_fields=["unit"])
        current = reorder_status(self.workspace)[0]
        self.assertTrue(current.mixed_units)
        self.assertFalse(current.needs_reorder)

    def test_ageing_preserves_lot_receipt_through_transfer_and_marks_unknown(self):
        record_stock_movement(self.workspace, self.owner, lot_id=self.lot.pk, kind="transfer",
                              source_id=self.a.pk, destination_id=self.b.pk, quantity=Decimal(2),
                              posted_on=self.day + timedelta(days=1), reference="SYN-TRANSFER", submission_key=uuid4())
        count_only_lot = register_lot(self.workspace, self.owner, code="COUNTED", product_id=self.product.pk)
        self.count("3", lot_id=count_only_lot.pk)
        rows = stock_ageing(self.workspace)
        self.assertEqual(len(rows), 3)
        for row in rows:
            if row.position.lot_id == count_only_lot.pk:
                self.assertIsNone(row.first_receipt)
                self.assertIsNone(row.age_days)
            else:
                self.assertEqual(row.first_receipt, date(2026, 5, 1))
                self.assertEqual(row.age_days, (timezone.localdate() - self.day).days)
        self.assertEqual(stock_ageing(self.foreign), [])
