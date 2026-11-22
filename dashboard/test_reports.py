from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import BusinessAccount, Customer, FollowUp, Quote, RFQ, TeamMembership


class BusinessReportTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username="report-owner", password="Report-Owner-Password-98!")
        self.account = BusinessAccount.objects.create(owner=self.owner, name="Report Steel Co")
        self.customer = Customer.objects.create(owner=self.owner, name="Report Customer")
        self.rfq = RFQ.objects.create(
            owner=self.owner, customer=self.customer, reference="REPORT-001", received_on=timezone.localdate(),
        )
        self.client.force_login(self.owner)

    def add_quote(self, status, number):
        timestamp = timezone.now()
        return Quote.objects.create(
            owner=self.owner, rfq=self.rfq, number=number, status=status,
            sent_at=timestamp if status in (Quote.Status.SENT, Quote.Status.ACCEPTED, Quote.Status.LOST) else None,
            closed_at=timestamp if status in (Quote.Status.ACCEPTED, Quote.Status.LOST) else None,
            target_margin_percent="12", minimum_margin_percent="8", maximum_discount_percent="5",
        )

    def test_report_calculates_workspace_pipeline_and_follow_up_rates(self):
        self.add_quote(Quote.Status.ACCEPTED, "QT-REPORT-1")
        self.add_quote(Quote.Status.LOST, "QT-REPORT-2")
        self.add_quote(Quote.Status.SENT, "QT-REPORT-3")
        FollowUp.objects.create(
            owner=self.owner, rfq=self.rfq, due_on=timezone.localdate() - timedelta(days=5),
            completed_at=timezone.now(),
        )
        FollowUp.objects.create(
            owner=self.owner, rfq=self.rfq, due_on=timezone.localdate() - timedelta(days=1),
        )

        response = self.client.get(reverse("dashboard:reports"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["win_rate"], Decimal("50.0"))
        self.assertEqual(response.context["accepted_count"], 1)
        self.assertEqual(response.context["lost_count"], 1)
        self.assertEqual(response.context["open_quote_count"], 1)
        self.assertEqual(response.context["overdue_follow_up_count"], 1)
        self.assertEqual(response.context["follow_up_completion_rate"], Decimal("50.0"))
        self.assertEqual(response.context["new_enquiry_count"], 1)

    def test_report_shares_company_counts_but_excludes_another_business(self):
        self.add_quote(Quote.Status.ACCEPTED, "QT-REPORT-1")
        teammate = get_user_model().objects.create_user(
            username="report-sales", email="report-sales@example.test", password="Report-Sales-Password-98!",
        )
        TeamMembership.objects.create(account=self.account, user=teammate, role=TeamMembership.Role.SALES)
        other = get_user_model().objects.create_user(username="other-report", password="Other-Report-Password-98!")
        other_customer = Customer.objects.create(owner=other, name="Other Report Customer")
        other_rfq = RFQ.objects.create(
            owner=other, customer=other_customer, reference="PRIVATE-REPORT", received_on=timezone.localdate(),
        )
        Quote.objects.create(
            owner=other, rfq=other_rfq, number="QT-OTHER-1", status=Quote.Status.ACCEPTED,
            sent_at=timezone.now(), closed_at=timezone.now(), target_margin_percent="12",
            minimum_margin_percent="8", maximum_discount_percent="5",
        )

        self.client.force_login(teammate)
        response = self.client.get(reverse("dashboard:reports"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["accepted_count"], 1)
        self.assertContains(response, "1 accepted")
        self.assertNotContains(self.client.get(reverse("dashboard:home")), "Open quotation value")
        self.assertNotContains(response, "PRIVATE-REPORT")

    def test_empty_report_handles_undefined_rates(self):
        response = self.client.get(reverse("dashboard:reports"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["win_rate"])
        self.assertIsNone(response.context["follow_up_completion_rate"])
        self.assertContains(response, "Win rate appears after")
