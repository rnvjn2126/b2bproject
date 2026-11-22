import csv
from io import StringIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import BusinessAccount, Customer, Supplier, TeamMembership


class RelationshipCSVExportTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username="export-owner", password="Export-Owner-Password-98!")
        self.other = user_model.objects.create_user(username="export-other", password="Export-Other-Password-98!")
        self.client.force_login(self.owner)

    def rows(self, response):
        return list(csv.reader(StringIO(response.content.decode("utf-8-sig"))))

    def test_customer_export_is_scoped_formula_safe_and_not_cached(self):
        Customer.objects.create(
            owner=self.owner, name='=HYPERLINK("https://example.invalid")',
            email="buyer@example.test", phone="+91 90000 00000", notes="+SUM(1,2)",
        )
        Customer.objects.create(owner=self.other, name="Private buyer", email="private@example.test")

        response = self.client.get(reverse("dashboard:customer_csv_export"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Disposition"], 'attachment; filename="steel-customers.csv"')
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        rows = self.rows(response)
        self.assertEqual(rows[0], ["name", "company_name", "email", "phone", "billing_address", "notes"])
        self.assertEqual(rows[1][0], "'=HYPERLINK(\"https://example.invalid\")")
        self.assertEqual(rows[1][5], "'+SUM(1,2)")
        self.assertNotIn("Private buyer", str(rows))

    def test_supplier_export_is_scoped_and_formula_safe(self):
        Supplier.objects.create(
            owner=self.owner, name="Steel source", company_name="=1+1", email="mill@example.test",
        )
        Supplier.objects.create(owner=self.other, name="Private source", email="private@example.test")

        response = self.client.get(reverse("dashboard:supplier_csv_export"))

        self.assertEqual(response.status_code, 200)
        rows = self.rows(response)
        self.assertEqual(rows[0], ["name", "company_name", "email", "phone", "address", "notes"])
        self.assertEqual(rows[1][1], "'=1+1")
        self.assertNotIn("Private source", str(rows))

    def test_company_members_share_contact_exports_and_exports_are_get_only(self):
        account = BusinessAccount.objects.create(owner=self.owner, name="Synthetic Export Co")
        member = get_user_model().objects.create_user(
            username="export-member", email="member@example.test", password="Export-Member-Password-98!",
        )
        TeamMembership.objects.create(account=account, user=member, role=TeamMembership.Role.SALES)
        Customer.objects.create(owner=self.owner, name="Shared company buyer")

        self.client.force_login(member)
        response = self.client.get(reverse("dashboard:customer_csv_export"))
        self.assertIn("Shared company buyer", str(self.rows(response)))
        self.assertEqual(self.client.post(reverse("dashboard:customer_csv_export")).status_code, 405)
        self.assertEqual(self.client.post(reverse("dashboard:supplier_csv_export")).status_code, 405)

        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:customer_csv_export")).status_code, 302)
        self.assertEqual(self.client.get(reverse("dashboard:supplier_csv_export")).status_code, 302)
