from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from . import test_movements
from .models import ReservationAction, StockMovement, StockPosition, StockReservation
from .reservations import record_reservation_action, reserve_stock
from .stock import record_stock_movement


class ReservationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        test_movements.StockMovementTests.setUpTestData.__func__(cls)
        cls.day = date(2026, 5, 1)
        record_stock_movement(cls.workspace, cls.owner, lot_id=cls.lot.pk, kind="receipt",
                              destination_id=cls.a.pk, quantity=Decimal("10"), posted_on=cls.day,
                              reference="SYN-RECEIPT", submission_key=uuid4())
        cls.position = StockPosition.objects.get(lot=cls.lot, location=cls.a)

    def hold(self, qty, **options):
        values = {"position_id": self.position.pk, "quantity": Decimal(qty), "posted_on": self.day,
                  "reference": "SYN-HOLD", "submission_key": uuid4()}
        return reserve_stock(self.workspace, self.owner, **(values | options))

    def test_reservation_blocks_ordinary_issue_and_can_release_or_fulfil(self):
        reservation = self.hold("8")
        self.assertEqual(self.hold("8", submission_key=reservation.submission_key), reservation)
        with self.assertRaisesMessage(ValidationError, "exceed available stock"):
            self.hold("3")
        with self.assertRaisesMessage(ValidationError, "exceed available stock"):
            record_stock_movement(self.workspace, self.owner, lot_id=self.lot.pk, kind="issue", source_id=self.a.pk,
                                  quantity=Decimal("3"), posted_on=self.day, reference="SYN", submission_key=uuid4())
        action = {"reservation_id": reservation.pk, "posted_on": self.day, "reference": "SYN-ACTION"}
        record_reservation_action(self.workspace, self.owner, **action, kind="release",
                                  quantity=Decimal("2"), submission_key=uuid4())
        issue_options = action | {"kind": "issue", "quantity": Decimal("4"), "submission_key": uuid4(),
                                  "actual_kg": Decimal("126.25")}
        issue = record_reservation_action(self.workspace, self.owner, **issue_options)
        self.assertEqual(record_reservation_action(self.workspace, self.owner, **issue_options), issue)
        self.assertEqual(issue.movement.actual_kg, Decimal("126.25"))
        self.position.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual((self.position.on_hand, self.position.reserved, self.position.available, reservation.remaining),
                         (Decimal("6"), Decimal("2"), Decimal("4"), Decimal("2")))
        self.assertEqual((StockMovement.objects.count(), ReservationAction.objects.count()), (2, 2))

    def test_reservation_issue_failure_rolls_back_and_other_company_has_no_access(self):
        reservation = self.hold("6")
        action = {"reservation_id": reservation.pk, "kind": "issue", "quantity": Decimal("3"),
                  "posted_on": self.day, "reference": "SYN-ISSUE", "submission_key": uuid4()}
        with patch("inventory.reservations.ReservationAction.objects.create", side_effect=IntegrityError):
            with self.assertRaises(IntegrityError):
                record_reservation_action(self.workspace, self.owner, **action)
        self.position.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual((self.position.on_hand, self.position.reserved, reservation.remaining),
                         (Decimal("10"), Decimal("6"), Decimal("6")))
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertFalse(ReservationAction.objects.exists())
        with self.assertRaises(ValidationError):
            record_reservation_action(self.foreign, self.other, **action)
        with self.assertRaisesMessage(ValidationError, "remaining reservation"):
            record_reservation_action(self.workspace, self.owner, **(action | {"quantity": Decimal("7")}))
        self.assertEqual(StockReservation.objects.count(), 1)
