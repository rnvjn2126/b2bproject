from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from dashboard.models import BusinessAccount

from .models import CompanyGSTRegistration, TaxRate
from .tax import calculate_line, invoice_total, validate_gstin
from .words import rupees_in_words


class GSTCalculationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.workspace = BusinessAccount.objects.create(owner=users.create_user(username="gst-owner"), name="Synthetic Steel")
        cls.other = BusinessAccount.objects.create(owner=users.create_user(username="gst-other"), name="Other synthetic company")
        cls.rate = TaxRate.objects.create(
            workspace=cls.workspace, item_kind="goods", item_code="000000", effective_from=date(2026, 4, 1),
            source_url="https://example.test/synthetic-only", integrated_rate=Decimal("12"),
            central_rate=Decimal("6"), local_rate=Decimal("6"), cess_rate=Decimal("1"),
        )

    def line(self, **overrides):
        data = {
            "quantity": Decimal("10"), "unit_price": Decimal("11.00"), "discount": Decimal("15.00"),
            "freight": Decimal("5.00"), "inclusive": False, "rate": self.rate,
            "supplier_state": "27", "place_of_supply": "27", "local_component": "sgst",
        }
        return calculate_line(**(data | overrides))

    def test_interstate_and_intrastate_use_distinct_components(self):
        local = self.line()
        self.assertEqual((local.taxable, local.cgst, local.sgst, local.igst, local.cess, local.total),
                         tuple(map(Decimal, ("100.00", "6.00", "6.00", "0", "1.00", "113.00"))))
        territory = self.line(supplier_state="04", place_of_supply="04", local_component="utgst")
        self.assertEqual((territory.sgst, territory.utgst, territory.total), (Decimal(0), Decimal("6.00"), Decimal("113")))
        interstate = self.line(place_of_supply="24")
        self.assertEqual((interstate.cgst, interstate.sgst, interstate.utgst, interstate.igst),
                         (Decimal(0), Decimal(0), Decimal(0), Decimal("12.00")))

    def test_inclusive_amount_and_round_off_reconcile_to_paise(self):
        line = self.line(quantity=Decimal("1"), unit_price=Decimal("113.05"), discount=Decimal(0),
                         freight=Decimal(0), inclusive=True)
        self.assertEqual(line.taxable, Decimal("100.05"))
        self.assertEqual(line.total, Decimal("113.05"))
        self.assertEqual(invoice_total([line, line], Decimal("-0.10")), Decimal("226.00"))
        rounded = self.line(quantity=Decimal("1"), unit_price=Decimal("1.25"),
                            discount=Decimal(0), freight=Decimal(0), place_of_supply="24")
        self.assertEqual(rounded.igst, Decimal("0.15"))
        self.assertEqual(rounded.cess, Decimal("0.01"))

    def test_rate_resolution_is_versioned_and_company_scoped(self):
        copy = {
            "item_kind": "goods", "item_code": "000000", "source_url": "https://example.test/synthetic-only",
            "integrated_rate": Decimal("10"), "central_rate": Decimal("5"), "local_rate": Decimal("5"),
        }
        later = TaxRate.objects.create(workspace=self.workspace, effective_from=date(2026, 8, 1), **copy)
        TaxRate.objects.create(workspace=self.other, effective_from=date(2026, 7, 1), **copy)
        self.assertIsNone(TaxRate.effective_for(self.workspace, "goods", "000000", date(2026, 3, 31)))
        self.assertEqual(TaxRate.effective_for(self.workspace, "goods", "000000", date(2026, 7, 15)), self.rate)
        self.assertEqual(TaxRate.effective_for(self.workspace, "goods", "000000", date(2026, 8, 1)), later)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TaxRate.objects.create(workspace=self.workspace, effective_from=later.effective_from, **copy)

    def test_unconfigured_and_invalid_inputs_do_not_silently_calculate(self):
        for inputs in (
            {"rate": None}, {"quantity": 10.0}, {"discount": Decimal("999")}, {"place_of_supply": "00"},
            {"unit_price": Decimal("NaN")}, {"freight": Decimal("0.001")},
        ):
            with self.subTest(inputs=inputs), self.assertRaises(ValidationError):
                self.line(**inputs)
        with self.assertRaises(ValidationError):
            validate_gstin("NOT-A-GSTIN")
        registration = CompanyGSTRegistration(workspace=self.workspace, gstin="27AAAAA0000A1Z0",
                                              registered_name="Synthetic", registered_address="Synthetic address")
        registration.full_clean()
        self.assertEqual(rupees_in_words(Decimal("12102034.05")),
                         "One crore twenty one lakh two thousand thirty four rupees and five paise only")
