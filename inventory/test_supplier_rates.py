from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from dashboard.models import Supplier

from . import tests as geometry_tests
from .models import SupplierDailyRate
from .supplier_rates import company_daily_rates, latest_daily_rates, recommend_procurement, record_daily_rate


D = Decimal


@override_settings(INTERNAL_INVENTORY=True)
class SupplierRateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        geometry_tests.SteelCatalogueTests.setUpTestData.__func__(cls)
        cls.product.unit = "kg"
        cls.product.save(update_fields=["unit"])
        cls.first = Supplier.objects.create(owner=cls.owner, name="Synthetic supplier A")
        cls.second = Supplier.objects.create(owner=cls.owner, name="Synthetic supplier B")
        cls.third = Supplier.objects.create(owner=cls.owner, name="Synthetic supplier C")
        cls.foreign_supplier = Supplier.objects.create(owner=cls.other, name="Foreign supplier")
        cls.day = timezone.localdate()

    def rate(self, **overrides):
        fields = dict(supplier_id=self.first.pk, product_id=self.product.pk, unit="kg", quoted_on=self.day,
                      valid_through=self.day + timedelta(days=1), unit_price=D("1"), available_quantity=D("600"),
                      freight=D("0"), packaging=D("0"), delivery_days=3, reference="SYN-RATE", submission_key=uuid4())
        return record_daily_rate(self.workspace, self.owner, **(fields | overrides))

    def suggest(self, quantity, **filters):
        return recommend_procurement(self.workspace, product_id=self.product.pk, quantity=D(quantity),
                                     as_of=self.day, **filters)

    def test_versions_and_expiry_never_reuse_an_older_superseded_offer(self):
        older = self.rate(quoted_on=self.day - timedelta(days=3))
        expired = self.rate(quoted_on=self.day - timedelta(days=2), valid_through=self.day - timedelta(days=1))
        self.assertEqual(list(latest_daily_rates(self.workspace, self.day)), [expired])
        self.assertEqual(self.suggest("10").unfilled, 10)
        latest = self.rate(unit_price=D("2"), available_quantity=D("0"))
        self.assertEqual(list(latest_daily_rates(self.workspace, self.day)), [latest])
        self.assertEqual(self.suggest("10").unfilled, 10)
        self.assertEqual(list(company_daily_rates(self.workspace)), [latest, expired, older])
        self.assertEqual(list(company_daily_rates(self.foreign)), [])

    def test_recommends_split_with_exact_charges_and_delivery_filter(self):
        a = self.rate(unit="tonne", available_quantity=D("0.600"), unit_price=D("1000"), freight=D("50"))
        b = self.rate(supplier_id=self.second.pk, unit_price=D("1.3"), packaging=D("12"), delivery_days=1)
        self.rate(supplier_id=self.third.pk, unit_price=D("1.4"), available_quantity=D("1200"), delivery_days=4)
        plan = self.suggest("1000")
        self.assertEqual([(line.rate, line.quantity, line.landed) for line in plan.lines],
                         [(a, 600, 650), (b, 400, 532)])
        self.assertEqual((plan.total, plan.unfilled, plan.delivery_days, plan.unit), (1182, 0, 3, "kg"))
        filtered = self.suggest("1000", max_delivery_days=2)
        self.assertEqual((filtered.total, filtered.unfilled, filtered.delivery_days), (792, 400, 1))

    def test_compares_fixed_charges_with_single_supplier(self):
        self.rate(available_quantity=D("900"), unit_price=D("0.5"))
        self.rate(supplier_id=self.second.pk, unit_price=D("0.1"), freight=D("400"))
        alternative = self.rate(supplier_id=self.third.pk, unit_price=D("0.8"), available_quantity=D("1000"))
        plan = self.suggest("1000")
        self.assertEqual([line.rate for line in plan.lines], [alternative])
        self.assertEqual(plan.total, 800)

    def test_scope_validation_and_idempotency(self):
        saved = self.rate()
        self.assertEqual(self.rate(submission_key=saved.submission_key), saved)
        with self.assertRaisesMessage(ValidationError, "different supplier rate"):
            self.rate(unit_price=D("2"), submission_key=saved.submission_key)
        with self.assertRaisesMessage(ValidationError, "from your company"):
            self.rate(supplier_id=self.foreign_supplier.pk)
        with self.assertRaisesMessage(ValidationError, "catalogue unit"):
            self.rate(unit="piece")
        with self.assertRaisesMessage(ValidationError, "valid-through"):
            self.rate(valid_through=self.day - timedelta(days=1))
        with self.assertRaises(PermissionDenied):
            record_daily_rate(self.workspace, self.other, supplier_id=self.first.pk, product_id=self.product.pk,
                              unit="kg", quoted_on=self.day, valid_through=self.day, unit_price=D(1), available_quantity=D(1),
                              freight=D(0), packaging=D(0), delivery_days=1, reference="SYN", submission_key=uuid4())
        self.assertEqual(SupplierDailyRate.objects.count(), 1)

    def test_private_rate_board_records_a_quote_and_shows_a_plan(self):
        url = reverse("accounting:inventory:supplier_rates")
        owner_client = Client(enforce_csrf_checks=True)
        owner_client.force_login(self.owner)
        response = owner_client.get(url)
        self.assertContains(response, "Supplier rate board")
        data = {
            "supplier_id": self.first.pk, "product_id": self.product.pk, "unit": "kg",
            "quoted_on": self.day.isoformat(), "valid_through": self.day.isoformat(), "unit_price": "20",
            "available_quantity": "3", "freight": "1", "packaging": "2", "delivery_days": "1",
            "reference": "SYN-OWNER-RATE", "submission_key": str(uuid4()),
        }
        self.assertEqual(owner_client.post(url, data).status_code, 403)
        data["csrfmiddlewaretoken"] = owner_client.cookies["csrftoken"].value
        self.assertRedirects(owner_client.post(url, data), url)
        plan = owner_client.get(url, {"plan-product_id": self.product.pk, "plan-quantity": "4"})
        for message in ("INR 63.00", "Unfilled quantity 1 kg", "SYN-OWNER-RATE"):
            self.assertContains(plan, message)
        self.assertIn("no-store", plan.headers["Cache-Control"])
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(url), "SYN-OWNER-RATE")
        self.assertContains(self.client.post(url, data), "Select a valid choice.")
        self.assertEqual(SupplierDailyRate.objects.count(), 1)
