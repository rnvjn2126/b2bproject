from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import BusinessAccount, TeamMembership, UserPreferences, QuotationDefaults, Customer, RFQ, AuditEvent


class CustomisationTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="prefs-owner")
        self.sales = get_user_model().objects.create_user(username="prefs-sales")
        self.other = get_user_model().objects.create_user(username="prefs-other")
        self.account = BusinessAccount.objects.create(owner=self.owner, name="Sample Company")
        self.member = TeamMembership.objects.create(user=self.sales, account=self.account, role="sales")
        self.url = reverse("dashboard:preferences")
        self.company = reverse("dashboard:company_defaults")

    def test_preferences_are_personal_validated_and_resettable(self):
        self.client.force_login(self.sales)
        data = {"theme": "dark", "text_size": "larger", "spacing": "compact", "reduce_motion": "on", "user": self.owner.pk}
        self.assertRedirects(self.client.post(self.url, data), self.url)
        self.assertEqual(UserPreferences.objects.get().user, self.sales)
        self.assertContains(self.client.get(reverse("dashboard:home")), 'data-theme="dark"')
        self.assertContains(self.client.get(reverse("dashboard:home")), 'data-text-size="larger"')
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(self.url), 'data-theme="system"')
        self.client.force_login(self.sales)
        data["theme"] = "invalid"
        self.assertEqual(self.client.post(self.url, data).status_code, 200)
        self.assertEqual(UserPreferences.objects.get().theme, "dark")
        self.client.post(self.url, {"action": "reset"})
        self.assertFalse(UserPreferences.objects.exists())

    def test_company_defaults_require_manager_role_and_scope(self):
        data = {"validity_days": 21, "payment_terms": "Payment on delivery", "delivery_terms": "Ex works", "account": 999}
        self.client.force_login(self.sales)
        self.assertEqual(self.client.post(self.company, data).status_code, 403)
        self.member.role = "manager"
        self.member.save()
        self.assertRedirects(self.client.post(self.company, data), self.company)
        self.assertEqual(QuotationDefaults.objects.get().account, self.account)
        self.assertTrue(AuditEvent.objects.filter(actor=self.sales, action="defaults_updated").exists())
        data["validity_days"] = 366
        self.assertEqual(self.client.post(self.company, data).status_code, 200)
        self.assertEqual(QuotationDefaults.objects.get().validity_days, 21)
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(self.company), "Payment on delivery")

    def test_new_quote_form_uses_shared_defaults(self):
        QuotationDefaults.objects.create(account=self.account, validity_days=21, payment_terms="30 days", delivery_terms="Ex works")
        customer = Customer.objects.create(owner=self.owner, name="Sample Buyer")
        rfq = RFQ.objects.create(owner=self.owner, customer=customer, received_on=timezone.localdate())
        self.client.force_login(self.sales)
        response = self.client.get(reverse("dashboard:quote_create", args=[rfq.pk]))
        form = response.context["form"]
        self.assertEqual(form.initial["payment_terms"], "30 days")
        self.assertEqual(form.initial["valid_until"], timezone.localdate() + timedelta(days=21))
        self.assertEqual(form.validity_days, 21)

    def test_login_csrf_and_post_methods(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.sales)
        self.assertEqual(client.post(self.url, {"action": "reset"}).status_code, 403)
        self.client.force_login(self.sales)
        self.assertEqual(self.client.put(self.url).status_code, 405)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertFalse(UserPreferences.objects.exists())
