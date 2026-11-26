from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from accounting.models import AccountGroup, Journal, Ledger
from dashboard.models import BusinessAccount, Customer, Quote, QuoteLine, RFQ, RFQLine, Supplier, SupplierOffer, TeamMembership
from orders.models import OrderMovement, PurchaseOrder, SalesOrder, SalesOrderLine

from .models import CompanyGSTRegistration, InvoiceDraft, TaxRate
from .posting import plan_invoice_posting, resolve_invoice_lines
from .services import prepare_draft
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


class InvoiceDraftTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.owner = users.create_user(username="draft-owner")
        cls.other = users.create_user(username="draft-other")
        cls.workspace = BusinessAccount.objects.create(owner=cls.owner, name="Synthetic drafts")
        cls.other_workspace = BusinessAccount.objects.create(owner=cls.other, name="Other draft workspace")
        cls.registration = CompanyGSTRegistration.objects.create(
            workspace=cls.workspace, gstin="27AAAAA0000A1Z0", registered_name="Synthetic Company",
            registered_address="Synthetic Company Address",
        )
        cls.rate = TaxRate.objects.create(
            workspace=cls.workspace, item_kind="goods", item_code="000000", effective_from=date(2026, 4, 1),
            source_url="https://example.test/synthetic-only", integrated_rate="12", central_rate="6", local_rate="6",
        )
        buyer = Customer.objects.create(owner=cls.owner, name="Synthetic Customer")
        supplier = Supplier.objects.create(owner=cls.owner, name="Synthetic Supplier", address="Synthetic Mill Address")
        day = date(2026, 5, 1)
        rfq = RFQ.objects.create(owner=cls.owner, customer=buyer, received_on=day)
        item = RFQLine.objects.create(owner=cls.owner, rfq=rfq, description="Synthetic steel", quantity="10", unit="kg")
        offer = SupplierOffer.objects.create(owner=cls.owner, rfq_line=item, supplier=supplier, available_quantity="10",
                                             unit_price="80", unit="kg", delivery_days=3)
        quote = Quote.objects.create(owner=cls.owner, rfq=rfq, number="SYN-1", target_margin_percent="20",
                                     minimum_margin_percent="10", maximum_discount_percent="5")
        quote_line = QuoteLine.objects.create(owner=cls.owner, quote=quote, rfq_line=item, supplier_offer=offer,
                                              quantity="10", unit="kg", selling_price_per_unit="100",
                                              landed_cost_per_unit="80", discount_percent="0")
        cls.order = SalesOrder.objects.create(
            workspace=cls.workspace, source_quote=quote, quotation_number=quote.number, quotation_revision=1,
            customer=buyer, customer_name=buyer.name, customer_address="Synthetic Customer Address",
            created_by=cls.owner, status=SalesOrder.Status.APPROVED,
        )
        sales_line = SalesOrderLine.objects.create(order=cls.order, quote_line=quote_line, description=item.description,
                                                   quantity="10", unit="kg", unit_price="100")
        purchase = PurchaseOrder.objects.create(
            requirement=sales_line, offer=offer, supplier=supplier, supplier_name=supplier.name, quantity="10",
            unit_price="80", delivery_on=day, submission_key=uuid4(), created_by=cls.owner, status=SalesOrder.Status.APPROVED,
        )
        cls.receipt = OrderMovement.objects.create(purchase_order=purchase, quantity="5", date=day, reference="SYN-R1",
                                                   recorded_by=cls.owner)
        cls.dispatch = OrderMovement.objects.create(sales_line=sales_line, quantity="3", date=day, reference="SYN-D1",
                                                    recorded_by=cls.owner)

    def draft(self, movement, workspace=None, actor=None, **overrides):
        args = {
            "movement_id": movement.pk, "registration_id": self.registration.pk, "party_gstin": "24BBBBB0000B1Z0",
            "item_code": "000000", "place_of_supply": "27", "local_component": "sgst", "inclusive": False,
            "discount": Decimal(0), "freight": Decimal(0), "round_off": Decimal(0),
        }
        return prepare_draft(workspace or self.workspace, actor or self.owner, **(args | overrides))

    def test_sales_and_purchase_drafts_use_confirmed_quantities_and_different_prices(self):
        sale = self.draft(self.dispatch)
        purchase = self.draft(self.receipt)
        self.assertEqual((sale.kind, sale.total, sale.snapshot["item"]["quantity"]), ("sales", Decimal("336"), "3.000"))
        self.assertEqual((purchase.kind, purchase.total), ("purchase", Decimal("448")))
        self.assertEqual(sale.snapshot["tax"]["sgst"], "18.00")
        self.assertEqual(purchase.snapshot["tax"]["igst"], "48.00")
        self.assertNotIn("Synthetic Supplier", str(sale.snapshot))
        self.assertFalse(Journal.objects.exists())

    def test_snapshot_survives_source_changes_and_rejects_duplicate_drafts(self):
        draft = self.draft(self.dispatch)
        TaxRate.objects.filter(pk=self.rate.pk).update(local_rate="5")
        CompanyGSTRegistration.objects.filter(pk=self.registration.pk).update(registered_name="Changed registration")
        draft.refresh_from_db()
        self.assertEqual(draft.snapshot["rate"]["local"], "6.0000")
        self.assertEqual(draft.snapshot["company"]["name"], "Synthetic Company")
        with self.assertRaisesMessage(ValidationError, "already has an internal invoice draft"):
            self.draft(self.dispatch)
        self.assertEqual(InvoiceDraft.objects.count(), 1)

    def test_draft_rejects_foreign_actor_foreign_sources_and_unapproved_order(self):
        with self.assertRaises(PermissionDenied):
            self.draft(self.dispatch, actor=self.other)
        with self.assertRaises(ValidationError):
            self.draft(self.dispatch, workspace=self.other_workspace, actor=self.other)
        other_reg = CompanyGSTRegistration.objects.create(
            workspace=self.other_workspace, gstin=self.registration.gstin, registered_name="Other",
            registered_address="Other Address",
        )
        with self.assertRaises(ValidationError):
            self.draft(self.dispatch, registration_id=other_reg.pk)
        with self.assertRaises(ValidationError):
            self.draft(self.dispatch, item_code="000001")
        SalesOrder.objects.filter(pk=self.order.pk).update(status=SalesOrder.Status.DRAFT)
        with self.assertRaises(ValidationError):
            self.draft(self.receipt)
        self.assertFalse(InvoiceDraft.objects.exists())


    def test_posting_plan_balances_sales_and_round_off(self):
        draft = self.draft(self.dispatch, round_off=Decimal("-0.01"))
        plan = plan_invoice_posting(draft)
        self.assertEqual(plan, [
            ("receivable", "D", Decimal("335.99")), ("sales", "C", Decimal("300.00")),
            ("output_cgst", "C", Decimal("18.00")), ("output_sgst", "C", Decimal("18.00")),
            ("round_off", "D", Decimal("0.01")),
        ])
        self.assertEqual(sum(amount for _, side, amount in plan if side == "D"),
                         sum(amount for _, side, amount in plan if side == "C"))
        self.assertFalse(Journal.objects.exists())

    def test_purchase_posting_plan_requires_explicit_input_tax_treatment(self):
        draft = self.draft(self.receipt, round_off=Decimal("0.01"))
        with self.assertRaisesMessage(ValidationError, "Explicitly confirm"):
            plan_invoice_posting(draft)
        claim = plan_invoice_posting(draft, recoverable_input_tax=True)
        expense = plan_invoice_posting(draft, recoverable_input_tax=False)
        self.assertEqual(claim, [
            ("payable", "C", Decimal("448.01")), ("purchases", "D", Decimal("400.00")),
            ("input_igst", "D", Decimal("48.00")), ("round_off", "D", Decimal("0.01")),
        ])
        self.assertEqual(expense, [
            ("payable", "C", Decimal("448.01")), ("purchases", "D", Decimal("448.00")),
            ("round_off", "D", Decimal("0.01")),
        ])
        self.assertFalse(Journal.objects.exists())

    def test_posting_plan_rejects_damaged_or_inconsistent_snapshots(self):
        draft = self.draft(self.dispatch)
        original = draft.snapshot["tax"].copy()
        for override in ({"cgst": "NaN"}, {"sgst": "-1"}, {"cess": "0.001"},
                         {"igst": "1"}, {"taxable": 300.00}, {"taxable": "299.99"}):
            with self.subTest(override=override), self.assertRaises(ValidationError):
                draft.snapshot["tax"] = original | override
                plan_invoice_posting(draft)
        self.assertFalse(Journal.objects.exists())

    def test_posting_proposal_resolves_only_distinct_company_ledgers_with_expected_kinds(self):
        draft = self.draft(self.dispatch)
        asset = AccountGroup.objects.create(workspace=self.workspace, code="A", name="Assets", kind="asset")
        income = AccountGroup.objects.create(workspace=self.workspace, code="I", name="Income", kind="income")
        liability = AccountGroup.objects.create(workspace=self.workspace, code="L", name="Liabilities", kind="liability")
        other_group = AccountGroup.objects.create(workspace=self.other_workspace, code="L", name="Other", kind="liability")

        def ledger(code, group, workspace=self.workspace):
            return Ledger.objects.create(workspace=workspace, code=code, name=code, group=group)

        ar, sales, cgst, sgst = [ledger(code, group) for code, group in (
            ("AR", asset), ("Sales", income), ("CGST", liability), ("SGST", liability),
        )]
        mapping = {"receivable": ar.pk, "sales": sales.pk, "output_cgst": cgst.pk, "output_sgst": sgst.pk}
        lines = resolve_invoice_lines(self.workspace, draft, mapping)
        self.assertEqual([account for account, _, _ in lines], [ar, sales, cgst, sgst])
        for bad in (None, ar.pk, cgst.pk, ledger("Other", other_group, self.other_workspace).pk,
                    ledger("Wrong group", other_group).pk):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                resolve_invoice_lines(self.workspace, draft, mapping | {"output_sgst": bad})
        with self.assertRaises(ValidationError):
            resolve_invoice_lines(self.other_workspace, draft, mapping)
        self.assertFalse(Journal.objects.exists())

    def test_purchase_proposal_uses_only_ledgers_required_by_selected_tax_treatment(self):
        draft = self.draft(self.receipt)
        accounts = {}
        for code, kind in (("PAY", "liability"), ("STOCK", "asset"), ("GST", "asset"), ("EXP", "expense")):
            group = AccountGroup.objects.create(workspace=self.workspace, code=code, name=code, kind=kind)
            accounts[code] = Ledger.objects.create(workspace=self.workspace, code=code, name=code, group=group)
        mapping = {"payable": accounts["PAY"].pk, "purchases": accounts["STOCK"].pk}
        with self.assertRaisesMessage(ValidationError, "every required invoice role"):
            resolve_invoice_lines(self.workspace, draft, mapping, recoverable_input_tax=True)
        with self.assertRaisesMessage(ValidationError, "wrong account classification"):
            resolve_invoice_lines(self.workspace, draft, mapping | {"input_igst": accounts["EXP"].pk},
                                  recoverable_input_tax=True)
        recover = resolve_invoice_lines(self.workspace, draft, mapping | {"input_igst": accounts["GST"].pk},
                                        recoverable_input_tax=True)
        expense = resolve_invoice_lines(self.workspace, draft, mapping | {"purchases": accounts["EXP"].pk},
                                        recoverable_input_tax=False)
        self.assertEqual(recover, [(accounts["PAY"], "C", Decimal("448.00")),
                                   (accounts["STOCK"], "D", Decimal("400.00")),
                                   (accounts["GST"], "D", Decimal("48.00"))])
        self.assertEqual(expense, [(accounts["PAY"], "C", Decimal("448.00")),
                                   (accounts["EXP"], "D", Decimal("448.00"))])
        self.assertFalse(Journal.objects.exists())

    def invoice_payload(self):
        return {
            "registration_id": self.registration.pk, "party_gstin": "24BBBBB0000B1Z0", "item_code": "000000",
            "place_of_supply": "27", "local_component": "sgst", "discount": "0", "freight": "0", "round_off": "0",
        }

    def test_owner_prepares_and_reopens_sales_and_purchase_drafts(self):
        self.client.force_login(self.owner)
        movements = reverse("accounting:invoice_movements")
        self.assertContains(self.client.get(movements), "SYN-D1")
        self.assertContains(self.client.get(movements), "SYN-R1")
        for movement, title, total in ((self.dispatch, "sales", "336.00"), (self.receipt, "purchase", "448.00")):
            with self.subTest(kind=title):
                prepare = reverse("accounting:invoice_prepare", args=[movement.pk])
                self.assertContains(self.client.get(prepare), "Save internal draft")
                response = self.client.post(prepare, self.invoice_payload())
                draft = InvoiceDraft.objects.get(movement=movement)
                detail = reverse("accounting:invoice_draft", args=[draft.pk])
                self.assertRedirects(response, detail)
                self.assertRedirects(self.client.post(prepare, self.invoice_payload()), detail)
                preview = self.client.get(detail)
                self.assertContains(preview, f"Internal {title} invoice draft")
                self.assertContains(preview, total)
                self.assertIn("no-store", preview.headers["Cache-Control"])
                self.assertEqual(self.client.post(detail).status_code, 405)
        self.assertEqual(InvoiceDraft.objects.count(), 2)
        self.assertFalse(Journal.objects.exists())

    def test_http_paths_enforce_owner_company_scope_and_csrf(self):
        movement = reverse("accounting:invoice_prepare", args=[self.dispatch.pk])
        self.client.force_login(self.owner)
        other_registration = CompanyGSTRegistration.objects.create(
            workspace=self.other_workspace, gstin="24BBBBB0000B1Z0", registered_name="Other", registered_address="Other",
        )
        response = self.client.post(movement, self.invoice_payload() | {"registration_id": other_registration.pk})
        self.assertTrue(response.context["form"].has_error("registration_id", "invalid_choice"))
        self.assertFalse(InvoiceDraft.objects.exists())
        valid_client = Client(enforce_csrf_checks=True)
        valid_client.force_login(self.owner)
        self.assertEqual(valid_client.post(movement, self.invoice_payload()).status_code, 403)
        draft = self.draft(self.dispatch)
        detail = reverse("accounting:invoice_draft", args=[draft.pk])
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse("accounting:invoice_movements")), "SYN-D1")
        self.assertEqual(self.client.post(movement, self.invoice_payload()).status_code, 404)
        self.assertEqual(self.client.get(detail).status_code, 404)
        manager = get_user_model().objects.create_user(username="draft-manager")
        TeamMembership.objects.create(account=self.workspace, user=manager, role=TeamMembership.Role.MANAGER)
        self.client.force_login(manager)
        self.assertEqual(self.client.get(detail).status_code, 403)
        self.assertEqual(self.client.post(movement, self.invoice_payload()).status_code, 403)


class GSTSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.owner = users.create_user(username="settings-owner")
        cls.other = users.create_user(username="settings-other")
        cls.staff = users.create_user(username="settings-staff")
        cls.workspace = BusinessAccount.objects.create(owner=cls.owner, name="Synthetic GST settings")
        other_workspace = BusinessAccount.objects.create(owner=cls.other, name="Other GST workspace")
        CompanyGSTRegistration.objects.create(
            workspace=other_workspace, gstin="27AAAAA0000A1Z0", registered_name="Private Other Company",
            registered_address="Other Address",
        )
        TeamMembership.objects.create(account=cls.workspace, user=cls.staff, role=TeamMembership.Role.MANAGER)

    def setUp(self):
        self.client.force_login(self.owner)
        self.url = reverse("accounting:gst_settings")
        self.registration = {
            "action": "registration", "registration-gstin": "27AAAAA0000A1Z0",
            "registration-registered_name": "Synthetic Company", "registration-registered_address": "Synthetic Address",
        }
        self.rate = {
            "action": "rate", "rate-item_kind": "goods", "rate-item_code": "000000",
            "rate-effective_from": "2026-04-01", "rate-source_url": "https://example.test/synthetic-only",
            "rate-integrated_rate": "12", "rate-central_rate": "6", "rate-local_rate": "6", "rate-cess_rate": "0",
        }

    def test_owner_can_add_registration_and_rate_once_and_view_only_own_company(self):
        self.assertRedirects(self.client.post(self.url, self.registration), self.url)
        self.assertRedirects(self.client.post(self.url, self.rate), self.url)
        for payload in (self.registration, self.rate):
            self.assertContains(self.client.post(self.url, payload), "already recorded for your company")
        self.assertEqual(CompanyGSTRegistration.objects.filter(workspace=self.workspace).count(), 1)
        self.assertEqual(TaxRate.objects.filter(workspace=self.workspace).count(), 1)
        response = self.client.get(self.url)
        self.assertContains(response, "Synthetic Company")
        self.assertContains(response, "https://example.test/synthetic-only")
        self.assertNotContains(response, "Private Other Company")
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_permissions_csrf_and_validation_prevent_invalid_records(self):
        self.assertContains(self.client.post(self.url, self.rate | {"rate-integrated_rate": "101"}),
                            "Enter a percentage between 0 and 100.")
        self.assertContains(self.client.post(self.url, self.rate | {"rate-item_kind": "service", "rate-item_code": "0000"}),
                            "Enter the six-digit SAC code.")
        self.assertContains(self.client.post(self.url, self.registration | {"registration-gstin": "INVALID"}),
                            "Enter a 15-character GSTIN")
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        self.assertEqual(csrf_client.post(self.url, self.registration).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.rate).status_code, 403)
        self.assertFalse(TaxRate.objects.exists())
        self.assertFalse(CompanyGSTRegistration.objects.filter(workspace=self.workspace).exists())
