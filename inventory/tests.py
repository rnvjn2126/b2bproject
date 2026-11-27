from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import SimpleTestCase, TestCase

from dashboard.models import BusinessAccount, Product

from .geometry import convert_quantity, cross_section_mm2
from .models import SteelSpecification
from .services import save_specification


class GeometryTests(SimpleTestCase):
    def test_theoretical_section_areas(self):
        d = Decimal
        for profile, dimensions, expected in (
            ("round", {"diameter": d(20)}, "314.159"),
            ("tmt", {"diameter": d(20)}, "314.159"),
            ("pipe", {"diameter": d(50), "thickness": d(2)}, "301.593"),
            ("sheet", {"width": d(1000), "thickness": d(2)}, "2000.000"),
            ("plate", {"width": d(1000), "thickness": d(2)}, "2000.000"),
            ("coil", {"width": d(1000), "thickness": d(2)}, "2000.000"),
            ("angle", {"width": d(40), "depth": d(30), "thickness": d(4)}, "264.000"),
            ("beam", {"width": d(75), "depth": d(150), "thickness": d(5), "flange": d(8)}, "1870.000"),
            ("channel", {"width": d(75), "depth": d(150), "thickness": d(5), "flange": d(8)}, "1870.000"),
        ):
            with self.subTest(profile=profile):
                self.assertEqual(cross_section_mm2(profile, **dimensions).quantize(d(".001")), d(expected))

    def test_invalid_geometry_and_conversion_are_rejected(self):
        with self.assertRaises(ValidationError):
            cross_section_mm2("pipe", diameter=Decimal("20"), thickness=Decimal("10"))
        with self.assertRaises(ValidationError):
            cross_section_mm2("angle", width=Decimal("20"), depth=Decimal("25"), thickness=Decimal("25"))
        with self.assertRaises(ValidationError):
            convert_quantity(Decimal("NaN"), "kg", "tonne")
        with self.assertRaises(ValidationError):
            convert_quantity(Decimal("1"), "kg", "piece")
        with self.assertRaises(ValidationError):
            convert_quantity(Decimal("1"), "kg", "m", measured_kg_per_m=Decimal("0"))


class SteelCatalogueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.owner = users.create_user(username="stock-owner")
        cls.other = users.create_user(username="stock-other")
        cls.workspace = BusinessAccount.objects.create(owner=cls.owner, name="Synthetic stockist")
        cls.foreign = BusinessAccount.objects.create(owner=cls.other, name="Other stockist")
        cls.product = Product.objects.create(owner=cls.owner, name="Sample sheet", grade="SYN-01", shape="sheet",
                                             dimensions="Legacy display dimensions", unit=Product.Unit.PIECE,
                                             weight_basis=Product.WeightBasis.ACTUAL, weight_kg="31.965")

    def test_catalogue_specification_and_measured_weight_remain_distinct(self):
        data = {"product_id": self.product.pk, "profile": "sheet", "grade": "",
                "density_kg_m3": Decimal("7850"), "width_mm": Decimal("1000"),
                "thickness_mm": Decimal("2"), "length_mm": Decimal("2000")}
        spec = save_specification(self.workspace, self.owner, **data)
        self.assertEqual((spec.grade, spec.theoretical_kg_per_m, spec.theoretical_kg_per_piece),
                         ("SYN-01", Decimal("15.7"), Decimal("31.4")))
        self.assertEqual(convert_quantity(Decimal("2"), "piece", "kg", specification=spec), Decimal("62.8"))
        self.assertEqual(convert_quantity(Decimal("62.8"), "kg", "piece", specification=spec), Decimal("2"))
        self.assertEqual(convert_quantity(Decimal("2"), "piece", "m", specification=spec), Decimal("4"))
        self.assertEqual(convert_quantity(Decimal("0.0628"), "tonne", "kg"), Decimal("62.8"))
        self.assertEqual(convert_quantity(Decimal("2"), "piece", "kg", specification=spec,
                                          measured_kg_per_m=Decimal("15.9825")), Decimal("63.93"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.weight_kg, Decimal("31.965"))
        self.assertEqual(self.product.dimensions, "Legacy display dimensions")
        self.assertEqual(save_specification(self.workspace, self.owner, **data).pk, spec.pk)
        self.assertEqual(SteelSpecification.objects.count(), 1)

    def test_specification_owner_and_product_boundaries(self):
        values = {"product_id": self.product.pk, "profile": "round", "grade": "SYN-01",
                  "density_kg_m3": Decimal("7850"), "diameter_mm": Decimal("10")}
        with self.assertRaises(PermissionDenied):
            save_specification(self.workspace, self.other, **values)
        with self.assertRaises(ValidationError):
            save_specification(self.foreign, self.other, **values)
        with self.assertRaises(ValidationError):
            save_specification(self.workspace, self.owner, **(values | {"diameter_mm": None}))
        self.assertFalse(SteelSpecification.objects.exists())
