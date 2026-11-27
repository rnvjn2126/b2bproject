from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from . import tests as geometry_tests
from .models import LotCertificate, StockLot, StorageLocation, Warehouse
from .services import save_specification
from .stock_setup import attach_lot_certificate, register_location, register_lot, register_warehouse


class StockSetupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        geometry_tests.SteelCatalogueTests.setUpTestData.__func__(cls)

    def test_warehouse_location_codes_and_scope(self):
        north = register_warehouse(self.workspace, self.owner, code=" north ", name="Synthetic North")
        south = register_warehouse(self.workspace, self.owner, code="south", name="Synthetic South")
        a = register_location(self.workspace, self.owner, warehouse_id=north.pk, code="A1", name="Rack 1")
        b = register_location(self.workspace, self.owner, warehouse_id=south.pk, code="A1", name="Rack 1")
        self.assertEqual(north.code, "NORTH")
        self.assertNotEqual(a, b)
        self.assertEqual(register_location(self.workspace, self.owner, warehouse_id=north.pk,
                                           code="a1", name="Rack 1"), a)
        with self.assertRaises(ValidationError):
            register_location(self.foreign, self.other, warehouse_id=north.pk, code="A2", name="Foreign rack")
        with self.assertRaises(PermissionDenied):
            register_warehouse(self.workspace, self.other, code="B1", name="Unauthorized")
        self.assertEqual((Warehouse.objects.count(), StorageLocation.objects.count()), (2, 2))

    def test_lot_snapshots_grade_geometry_and_identifiers(self):
        fields = {"product_id": self.product.pk, "profile": "sheet", "grade": "SYN-GRADE",
                  "density_kg_m3": Decimal("7850"), "width_mm": Decimal("1000"),
                  "thickness_mm": Decimal("2"), "length_mm": Decimal("2000")}
        save_specification(self.workspace, self.owner, **fields)
        identity = {"code": "lot-1", "product_id": self.product.pk, "heat_number": "H1", "batch_number": "B1",
                    "mill_name": "Synthetic mill", "manufacturer_name": "Synthetic producer"}
        lot = register_lot(self.workspace, self.owner, **identity)
        self.assertEqual((lot.unit, lot.grade, lot.nominal_kg_per_m, lot.length_mm),
                         ("piece", "SYN-GRADE", Decimal("15.7"), Decimal("2000")))
        self.assertEqual((lot.heat_number, lot.batch_number, lot.manufacturer_name), ("H1", "B1", "Synthetic producer"))
        save_specification(self.workspace, self.owner, **(fields | {"thickness_mm": Decimal("3")}))
        self.assertEqual(register_lot(self.workspace, self.owner, **identity).nominal_kg_per_m, Decimal("15.7"))
        with self.assertRaises(ValidationError):
            register_lot(self.workspace, self.owner, **(identity | {"heat_number": "different"}))
        with self.assertRaises(ValidationError):
            register_lot(self.foreign, self.other, **identity)
        self.assertEqual(StockLot.objects.count(), 1)

    def test_certificate_evidence_replays_and_rejects_changed_or_foreign_upload(self):
        lot = register_lot(self.workspace, self.owner, code="lot-cert", product_id=self.product.pk)
        content = b"%PDF-1.4\n% Synthetic evidence only\n%%EOF\n"
        receipt = attach_lot_certificate(self.workspace, self.owner, lot_id=lot.pk, content=content)
        self.assertEqual(bytes(receipt.content), content)
        self.assertEqual(attach_lot_certificate(self.workspace, self.owner, lot_id=lot.pk, content=content), receipt)
        with self.assertRaises(ValidationError):
            attach_lot_certificate(self.workspace, self.owner, lot_id=lot.pk, content=b"<html>synthetic</html>")
        with self.assertRaises(ValidationError):
            attach_lot_certificate(self.workspace, self.owner, lot_id=lot.pk, content=content.replace(b"1.4", b"1.7"))
        with self.assertRaises(ValidationError):
            attach_lot_certificate(self.foreign, self.other, lot_id=lot.pk, content=content)
        self.assertEqual(LotCertificate.objects.count(), 1)
