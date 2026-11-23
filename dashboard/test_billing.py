import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .billing import apply_billing_event, current_plan, reserve_quotation, used_quotations
from .models import BillingEvent, BusinessAccount, Customer, MonthlyUsage, SubscriptionPeriod, TeamInvitation, TeamMembership, RFQ, RFQLine, Supplier, SupplierOffer, Quote


@override_settings(DEBUG=True, BILLING_SANDBOX_ENABLED=True)
class BillingTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="billing-owner")
        self.account = BusinessAccount.objects.create(owner=self.owner, name="Synthetic Billing Co")
        self.other = get_user_model().objects.create_user(username="billing-outsider")
        self.client.force_login(self.owner)

    def purchase(self, tier="small", months=1):
        return SubscriptionPeriod.objects.create(account=self.account, tier=tier, months=months)

    def event(self, purchase, outcome="paid", event_id=None):
        return {"id": event_id or str(uuid.uuid4()), "purchase_id": str(purchase.pk), "outcome": outcome}

    def test_plan_catalogue_and_free_defaults(self):
        response = Client().get(reverse("dashboard:plans"))
        for name in ("Free", "Small Business", "Medium Business", "Large Business"):
            self.assertContains(response, name)
        self.assertEqual(current_plan(self.account)["quotations"], 5)
        self.assertEqual(current_plan(self.account)["seats"], 1)
        self.assertContains(response, "No card details")

    def test_signup_creates_free_workspace_and_cannot_assign_privileges(self):
        client = Client()
        data = {"username": "new-owner", "email": "new@example.test", "company_name": "Sample Startup",
                "password1": "Granite-River-Company-2047!", "password2": "Granite-River-Company-2047!",
                "is_staff": "1", "is_superuser": "1", "tier": "large"}
        with override_settings(PUBLIC_SIGNUP_ENABLED=True):
            response = client.post(reverse("dashboard:signup"), data)
        self.assertRedirects(response, reverse("dashboard:home"))
        user = get_user_model().objects.get(username="new-owner")
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(current_plan(user.business_account)["tier"], "free")
        self.assertFalse(SubscriptionPeriod.objects.filter(account=user.business_account).exists())
        client.logout()
        data["username"] = "duplicate-email"
        with override_settings(PUBLIC_SIGNUP_ENABLED=True):
            response = client.post(reverse("dashboard:signup"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="duplicate-email").exists())
        with override_settings(PUBLIC_SIGNUP_ENABLED=False):
            self.assertEqual(client.post(reverse("dashboard:signup"), data).status_code, 403)

    def test_checkout_is_owner_scoped_validated_and_get_cannot_activate(self):
        create = reverse("dashboard:checkout_create")
        self.assertEqual(self.client.get(create).status_code, 405)
        self.assertEqual(self.client.post(create, {"tier": "admin", "months": "1"}).status_code, 400)
        self.assertEqual(self.client.post(create, {"tier": "small", "months": "1200"}).status_code, 400)
        response = self.client.post(create, {"tier": "small", "months": "1", "account": 999})
        purchase = SubscriptionPeriod.objects.get()
        self.assertEqual(purchase.account, self.account)
        self.client.get(response.url + "?outcome=paid")
        self.assertEqual(current_plan(self.account)["tier"], "free")
        self.client.post(create, {"tier": "small", "months": "1"})
        self.assertEqual(SubscriptionPeriod.objects.count(), 1)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(response.url).status_code, 404)
        self.assertEqual(self.client.post(response.url, {"outcome": "paid"}).status_code, 404)
        TeamMembership.objects.create(account=self.account, user=self.other, role="manager")
        self.assertEqual(self.client.post(create, {"tier": "large", "months": "1"}).status_code, 403)
        self.assertNotContains(self.client.get(reverse("dashboard:billing")), str(purchase.pk))

    def test_checkout_changes_cancel_previous_order(self):
        create = reverse("dashboard:checkout_create")
        self.client.post(create, {"tier": "small", "months": "1"})
        old = SubscriptionPeriod.objects.get()
        self.client.post(create, {"tier": "medium", "months": "12"})
        old.refresh_from_db()
        self.assertEqual(old.status, "cancelled")
        apply_billing_event(self.event(old))
        self.assertEqual(current_plan(self.account)["tier"], "free")

    def test_success_is_idempotent_and_late_failure_does_not_revoke(self):
        purchase = self.purchase()
        payload = self.event(purchase)
        confirmed = apply_billing_event(payload)
        first_end = confirmed.ends_at
        self.assertEqual(current_plan(self.account)["tier"], "small")
        apply_billing_event(payload)
        apply_billing_event(self.event(purchase))
        apply_billing_event(self.event(purchase, "failed"))
        confirmed.refresh_from_db()
        self.assertEqual(confirmed.ends_at, first_end)
        self.assertEqual(confirmed.status, "paid")
        self.assertEqual(BillingEvent.objects.filter(event_id=payload["id"]).count(), 1)
        with self.assertRaises(ValidationError):
            apply_billing_event({**payload, "outcome": "refunded"})

    def test_failure_refund_and_out_of_order_success(self):
        purchase = self.purchase()
        apply_billing_event(self.event(purchase, "failed"))
        self.assertEqual(current_plan(self.account)["tier"], "free")
        apply_billing_event(self.event(purchase, "refunded"))
        apply_billing_event(self.event(purchase))
        self.assertEqual(current_plan(self.account)["tier"], "free")
        next_purchase = self.purchase("medium")
        apply_billing_event(self.event(next_purchase))
        Customer.objects.create(owner=self.owner, name="Retained customer")
        apply_billing_event(self.event(next_purchase, "refunded"))
        self.assertEqual(current_plan(self.account)["tier"], "free")
        self.assertTrue(Customer.objects.filter(owner=self.owner).exists())

    def test_renewal_queues_access_without_resetting_usage_and_refunds_are_scoped(self):
        first = apply_billing_event(self.event(self.purchase()))
        MonthlyUsage.objects.create(account=self.account, month=timezone.localdate().replace(day=1), quotations=4)
        second = apply_billing_event(self.event(self.purchase("large", months=12)))
        self.assertEqual(second.starts_at, first.ends_at)
        self.assertEqual(current_plan(self.account)["tier"], "small")
        self.assertEqual(used_quotations(self.account, self.owner), 4)
        apply_billing_event(self.event(second, "refunded"))
        self.assertEqual(current_plan(self.account)["tier"], "small")
        with patch("dashboard.billing.timezone.now", return_value=first.ends_at):
            self.assertEqual(current_plan(self.account)["tier"], "free")

    def test_calendar_terms_handle_month_end_and_leap_year(self):
        for start, months, expected in (
            (datetime(2028, 1, 31, 12, tzinfo=ZoneInfo("Asia/Kolkata")), 1, (2028, 2, 29)),
            (datetime(2028, 2, 29, 12, tzinfo=ZoneInfo("Asia/Kolkata")), 12, (2029, 2, 28)),
        ):
            BillingEvent.objects.all().delete()
            SubscriptionPeriod.objects.all().delete()
            purchase = self.purchase(months=months)
            with patch("dashboard.billing.timezone.now", return_value=start):
                paid = apply_billing_event(self.event(purchase))
            local_end = timezone.localtime(paid.ends_at)
            self.assertEqual((local_end.year, local_end.month, local_end.day), expected)

    def test_production_never_activates_sandbox_access(self):
        purchase = self.purchase()
        apply_billing_event(self.event(purchase))
        with override_settings(DEBUG=False):
            self.assertEqual(current_plan(self.account)["tier"], "free")
            response = self.client.post(reverse("dashboard:checkout", args=[purchase.pk]), {"outcome": "paid"})
            self.assertEqual(response.status_code, 403)
            self.assertEqual(self.client.post(reverse("dashboard:checkout_create"), {"tier": "large", "months": "1"}).status_code, 403)
            with self.assertRaises(ValidationError):
                apply_billing_event(self.event(purchase))

    def test_csrf_and_cancellation(self):
        purchase = self.purchase()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        url = reverse("dashboard:checkout", args=[purchase.pk])
        self.assertEqual(client.post(url, {"outcome": "paid"}).status_code, 403)
        response = client.get(url)
        token = response.cookies["csrftoken"].value
        self.assertEqual(client.post(url, {"outcome": "paid"}, HTTP_X_CSRFTOKEN=token).status_code, 302)
        pending = self.purchase()
        cancel = reverse("dashboard:cancel_checkout", args=[pending.pk])
        self.assertEqual(self.client.get(cancel).status_code, 405)
        self.client.post(cancel)
        apply_billing_event(self.event(pending))
        pending.refresh_from_db()
        self.assertEqual(pending.status, "cancelled")

    @override_settings(BILLING_WEBHOOK_SECRET="synthetic-webhook-secret-only-for-tests-2047")
    def test_webhook_verifies_signature_duplicates_and_malformed_events(self):
        from django.conf import settings
        purchase = self.purchase()
        url = reverse("dashboard:billing_test_webhook")
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.get(url).status_code, 405)
        payload = self.event(purchase)
        body = json.dumps(payload).encode()
        signature = hmac.new(settings.BILLING_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        self.assertEqual(client.post(url, body, content_type="application/json").status_code, 403)
        self.assertEqual(current_plan(self.account)["tier"], "free")
        for _ in range(2):
            response = client.post(url, body, content_type="application/json", HTTP_X_STEEL_QUOTES_SIGNATURE=signature)
            self.assertEqual(response.status_code, 200)
        self.assertEqual(BillingEvent.objects.count(), 1)
        self.assertEqual(client.post(url, body + b" ", content_type="application/json", HTTP_X_STEEL_QUOTES_SIGNATURE=signature).status_code, 403)
        for invalid in ([], {}, {"id": "bad", "outcome": [], "purchase_id": "x"}, {**payload, "purchase_id": "bad-uuid"}):
            raw = json.dumps(invalid).encode()
            sig = hmac.new(settings.BILLING_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
            self.assertEqual(client.post(url, raw, content_type="application/json", HTTP_X_STEEL_QUOTES_SIGNATURE=sig).status_code, 400)
        with override_settings(DEBUG=False):
            self.assertEqual(client.post(url, body, content_type="application/json", HTTP_X_STEEL_QUOTES_SIGNATURE=signature).status_code, 503)

    def test_usage_limit_rolls_back_with_failed_save_and_resets_monthly(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.assertTrue(reserve_quotation(self.account))
                raise RuntimeError("simulated failed quote save")
        self.assertFalse(MonthlyUsage.objects.exists())
        for _ in range(5):
            with transaction.atomic():
                self.assertTrue(reserve_quotation(self.account))
        with transaction.atomic():
            self.assertFalse(reserve_quotation(self.account))
        next_month = (timezone.localdate().replace(day=28) + timedelta(days=4)).replace(day=1)
        with patch("dashboard.billing.timezone.localdate", return_value=next_month):
            with transaction.atomic():
                self.assertTrue(reserve_quotation(self.account))
        self.assertEqual(MonthlyUsage.objects.count(), 2)

    def test_free_paywalls_and_expired_member_read_only_access(self):
        for name in ("reports", "company_defaults", "product_csv_import"):
            self.assertEqual(self.client.get(reverse("dashboard:" + name)).status_code, 403)
        paid = apply_billing_event(self.event(self.purchase()))
        TeamMembership.objects.create(account=self.account, user=self.other, role="sales")
        Customer.objects.create(owner=self.owner, name="Shared business customer")
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse("dashboard:customer_create"), {"name": "Allowed while paid"}).status_code, 302)
        apply_billing_event(self.event(paid, "refunded"))
        self.assertContains(self.client.get(reverse("dashboard:customer_list")), "Shared business customer")
        self.assertEqual(self.client.get(reverse("dashboard:customer_csv_export")).status_code, 200)
        self.assertEqual(self.client.post(reverse("dashboard:customer_create"), {"name": "Blocked after expiry"}).status_code, 403)
        self.assertFalse(Customer.objects.filter(name="Blocked after expiry").exists())
        self.assertEqual(self.client.post(reverse("dashboard:preferences"), {"action": "reset"}).status_code, 302)

    def test_pending_invitations_reserve_seats_and_expiry_blocks_acceptance(self):
        paid = apply_billing_event(self.event(self.purchase()))
        url = reverse("dashboard:team_list")
        for index in range(2):
            self.assertEqual(self.client.post(url, {"action": "invite", "email": f"member{index}@example.test", "role": "sales"}).status_code, 302)
        invite_url = self.client.session["team_invite_url"]
        response = self.client.post(url, {"action": "invite", "email": "excess@example.test", "role": "sales"})
        self.assertContains(response, "user allowance is full")
        self.assertEqual(TeamInvitation.objects.count(), 2)
        apply_billing_event(self.event(paid, "refunded"))
        self.client.logout()
        self.assertEqual(self.client.post(invite_url, {}).status_code, 403)
        self.assertEqual(TeamMembership.objects.count(), 0)


class QuotationAllowanceTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="quota-owner")
        self.account = BusinessAccount.objects.create(owner=self.owner, name="Quota Sample Co")
        self.customer = Customer.objects.create(owner=self.owner, name="Synthetic Buyer")
        self.supplier = Supplier.objects.create(owner=self.owner, name="Synthetic Mill")
        self.rfq = RFQ.objects.create(owner=self.owner, customer=self.customer, received_on=timezone.localdate())
        self.line = RFQLine.objects.create(owner=self.owner, rfq=self.rfq, description="Test plate", quantity=100, unit="kg")
        self.offer = SupplierOffer.objects.create(owner=self.owner, rfq_line=self.line, supplier=self.supplier,
                                                  available_quantity=100, unit="kg", unit_price=90, delivery_days=3)
        self.url = reverse("dashboard:quote_create", args=[self.rfq.pk])
        self.data = {f"offer_{self.line.pk}": self.offer.pk, f"discount_{self.line.pk}": "0"}
        self.client.force_login(self.owner)

    def test_last_slot_is_consumed_once_and_preview_does_not_consume(self):
        usage = MonthlyUsage.objects.create(account=self.account, month=timezone.localdate().replace(day=1), quotations=4)
        self.assertEqual(self.client.post(self.url, {**self.data, "action": "preview"}).status_code, 200)
        usage.refresh_from_db()
        self.assertEqual(usage.quotations, 4)
        self.assertEqual(self.client.post(self.url, self.data).status_code, 302)
        self.assertEqual(self.client.post(self.url, self.data).status_code, 403)
        usage.refresh_from_db()
        self.assertEqual(usage.quotations, 5)
        self.assertEqual(Quote.objects.count(), 1)
        quote = Quote.objects.get()
        self.assertEqual(self.client.post(reverse("dashboard:quote_revision_create", args=[quote.pk]), self.data).status_code, 403)
        self.assertEqual(self.client.get(reverse("dashboard:quote_pdf", args=[quote.pk])).status_code, 200)
        self.assertEqual(self.client.post(self.url, {**self.data, "action": "preview"}).status_code, 200)

    def test_invalid_or_failed_quote_save_does_not_consume_allowance(self):
        self.assertEqual(self.client.post(self.url, {**self.data, f"discount_{self.line.pk}": "100"}).status_code, 200)
        self.assertFalse(MonthlyUsage.objects.exists())
        with patch("dashboard.models.QuoteLine.save", side_effect=RuntimeError("synthetic database failure")):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, self.data)
        self.assertFalse(Quote.objects.exists())
        self.assertFalse(MonthlyUsage.objects.exists())

    def test_legacy_quotes_count_and_paid_workspace_members_share_allowance(self):
        from .test_helpers import grant_test_plan
        for number in range(5):
            Quote.objects.create(owner=self.owner, rfq=self.rfq, number=f"LEGACY-{number}",
                                 target_margin_percent=12, minimum_margin_percent=8, maximum_discount_percent=5)
        self.assertEqual(self.client.post(self.url, self.data).status_code, 403)
        grant_test_plan(self.owner)
        member = get_user_model().objects.create_user(username="quota-member")
        TeamMembership.objects.create(account=self.account, user=member, role="sales")
        self.client.force_login(member)
        self.assertEqual(self.client.post(self.url, self.data).status_code, 302)
        self.assertEqual(MonthlyUsage.objects.get(account=self.account).quotations, 6)
        self.assertFalse(Quote.objects.filter(owner=member).exists())
