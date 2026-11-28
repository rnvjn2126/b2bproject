from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from accounting.models import Journal
from dashboard.models import Product

from . import test_movements
from .costing import CostMethod
from .cutting import CutOutput, record_stock_cut
from .models import StockCut, StockMovement, StockPosition
from .reservations import reserve_stock
from .stock import record_stock_movement
from .stock_setup import register_lot
from .valuation import set_valuation_method, value_stock_movement


D = Decimal


class StockCutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        test_movements.StockMovementTests.setUpTestData.__func__(cls)
        cls.day = date(2026, 5, 1)
        set_valuation_method(cls.workspace, cls.owner, method=CostMethod.FIFO)
        source = record_stock_movement(
            cls.workspace, cls.owner, lot_id=cls.lot.pk, destination_id=cls.a.pk, kind="receipt", quantity=D(5),
            actual_kg=D(50), posted_on=cls.day, reference="SYN-INPUT", submission_key=uuid4(),
        )
        value_stock_movement(cls.workspace, cls.owner, movement_id=source.pk, material=D("500"))
        cls.target_lots = []
        for name, unit in (("Finished", "piece"), ("Remnant", "m"), ("Scrap", "kg")):
            product = Product.objects.create(owner=cls.owner, name=f"Synthetic {name}", grade=cls.lot.grade,
                                             shape="sheet", unit=unit)
            cls.target_lots.append(register_lot(cls.workspace, cls.owner, code=name.upper(), product_id=product.pk))

    def inputs(self):
        return dict(
            lot_id=self.lot.pk, source_id=self.a.pk, quantity=D(4), actual_kg=D(40), reference="SYN-CUT",
            posted_on=self.day, submission_key=uuid4(), outputs=[
                CutOutput("finished", self.target_lots[0].pk, self.b.pk, D(2), D(25)),
                CutOutput("remnant", self.target_lots[1].pk, self.b.pk, D("1.3"), D(10)),
                CutOutput("scrap", self.target_lots[2].pk, self.a.pk, D(5), D(5)),
            ],
        )

    def test_cut_conserves_measured_mass_and_inventory_value_and_replays(self):
        values = self.inputs()
        cut = record_stock_cut(self.workspace, self.owner, **values)
        self.assertEqual(record_stock_cut(self.workspace, self.owner, **values), cut)
        self.assertEqual(cut.source.amount, 400)
        self.assertEqual(cut.source.closing_amount, 100)
        self.assertEqual(list(cut.outputs.values_list("kind", "receipt__amount")), [
            ("finished", D(250)), ("remnant", D(100)), ("scrap", D(50)),
        ])
        self.assertEqual(sum(cut.outputs.values_list("receipt__movement__actual_kg", flat=True)), 40)
        self.assertEqual(dict(StockPosition.objects.values_list("lot_id", "on_hand")),
                         {self.lot.pk: D(1), self.target_lots[0].pk: D(2),
                          self.target_lots[1].pk: D("1.3"), self.target_lots[2].pk: D(5)})
        self.assertEqual(StockMovement.objects.count(), 5)
        self.assertFalse(Journal.objects.exists())
        with self.assertRaisesMessage(ValidationError, "different cut"):
            record_stock_cut(self.workspace, self.owner, **(values | {"reference": "CHANGED"}))
        with self.assertRaisesMessage(IntegrityError, "immutable"), transaction.atomic():
            StockCut.objects.filter(pk=cut.pk).update(fingerprint="changed")

    def test_invalid_mass_scope_and_reservations_leave_no_cut(self):
        values = self.inputs()
        with self.assertRaisesMessage(ValidationError, "Measured output weights"):
            record_stock_cut(self.workspace, self.owner, **(values | {"actual_kg": D(39)}))
        bad_location = CutOutput("scrap", self.target_lots[2].pk, self.c.pk, D(5), D(5))
        with self.assertRaisesMessage(ValidationError, "locations in this company"):
            record_stock_cut(self.workspace, self.owner, **(values | {"outputs": [*values["outputs"][:2], bad_location]}))
        bad_lot = register_lot(self.workspace, self.owner, code="WRONG-HEAT", product_id=self.target_lots[2].product_id,
                               heat_number="SYN-DIFFERENT")
        with self.assertRaisesMessage(ValidationError, "mill traceability"):
            record_stock_cut(self.workspace, self.owner, **(values | {"outputs": [
                *values["outputs"][:2], CutOutput("scrap", bad_lot.pk, self.a.pk, D(5), D(5)),
            ]}))
        position = StockPosition.objects.get(lot=self.lot, location=self.a)
        reserve_stock(self.workspace, self.owner, position_id=position.pk, quantity=D(2), posted_on=self.day,
                      reference="SYN-HOLD", submission_key=uuid4())
        with self.assertRaisesMessage(ValidationError, "available stock"):
            record_stock_cut(self.workspace, self.owner, **values)
        with self.assertRaises(PermissionDenied):
            record_stock_cut(self.workspace, self.other, **values)
        position.refresh_from_db()
        self.assertEqual((position.on_hand, position.reserved), (5, 2))
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertFalse(StockCut.objects.exists())

    @override_settings(INTERNAL_INVENTORY=True)
    def test_owner_cut_form_saves_finished_stock_and_scrap(self):
        self.client.force_login(self.owner)
        url = reverse("accounting:inventory:cut_stock")
        self.assertContains(self.client.get(url), "Steel cutting")
        values = self.inputs()
        form = {key: str(value) for key, value in values.items() if key != "outputs"}
        form |= {"outputs-TOTAL_FORMS": "3", "outputs-INITIAL_FORMS": "0"}
        for index, output in enumerate(values["outputs"]):
            form |= {f"outputs-{index}-{key}": str(value) for key, value in vars(output).items()}
        self.assertRedirects(self.client.post(url, form), url)
        screen = self.client.get(url)
        self.assertContains(screen, "Recoverable scrap")
        self.assertContains(screen, "INR 50.00")
        self.assertIn("no-store", screen.headers["Cache-Control"])
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(url), "SYN-CUT")
