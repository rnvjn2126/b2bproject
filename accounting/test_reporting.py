from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from dashboard.models import BusinessAccount, TeamMembership

from .models import AccountGroup, Journal, Ledger
from .reporting import comparison_dates, financial_overview
from .services import post_journal, setup_books
from .templatetags.indian_finance import inr


D = Decimal


class ReportFormattingTests(SimpleTestCase):
    def test_indian_grouping_and_leap_day_comparison(self):
        self.assertEqual(inr(D("-12345678.95")), "−₹1,23,45,678.95")
        self.assertEqual(inr(D(1234)), "₹1,234.00")
        self.assertEqual(comparison_dates(date(2024, 2, 29), date(2024, 3, 4), "prior-year"),
                         (date(2023, 2, 28), date(2023, 3, 4)))
        self.assertEqual(comparison_dates(date(2026, 5, 1), date(2026, 5, 3), "previous"),
                         (date(2026, 4, 28), date(2026, 4, 30)))


class FinanceDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.owner = users.create_user(username="synthetic-finance")
        cls.member = users.create_user(username="synthetic-manager")
        other = users.create_user(username="foreign-finance")
        cls.workspace = BusinessAccount.objects.create(owner=cls.owner, name="Synthetic Finance")
        cls.foreign = BusinessAccount.objects.create(owner=other, name="Foreign Finance")
        TeamMembership.objects.create(account=cls.workspace, user=cls.member, role=TeamMembership.Role.MANAGER)
        cls.year = setup_books(cls.workspace, cls.owner, 2026)
        cls.foreign_year = setup_books(cls.foreign, other, 2026)
        loan = AccountGroup.objects.get(workspace=cls.workspace, code="LIABILITY-2")
        Ledger.objects.create(workspace=cls.workspace, code="SYN-LOAN", name="Synthetic loan", group=loan)
        cls.ledgers = {ledger.code: ledger for ledger in Ledger.objects.filter(workspace=cls.workspace)}
        cls.start = date(2026, 4, 1)
        cls.end = date(2026, 5, 1)
        fixture = cls()
        fixture.post(cls.start, Journal.Kind.OPENING, [("1010", "D", "100"), ("3000", "C", "100")])
        fixture.post(cls.end, Journal.Kind.RECEIPT, [("1000", "D", "80"), ("4000", "C", "80")])
        fixture.post(cls.end, Journal.Kind.PAYMENT, [("5200", "D", "10"), ("1000", "C", "10")])
        fixture.post(cls.end, Journal.Kind.PAYMENT, [("1500", "D", "20"), ("1010", "C", "20")])
        fixture.post(cls.end, Journal.Kind.RECEIPT, [("1010", "D", "30"), ("SYN-LOAN", "C", "30")])
        fixture.post(cls.end, Journal.Kind.CONTRA, [("1010", "D", "5"), ("1000", "C", "5")])
        fixture.post(cls.end, Journal.Kind.GENERAL, [("1010", "D", "15"), ("3000", "C", "8"), ("4000", "C", "7")])

    def post(self, day, kind, lines):
        return post_journal(
            self.workspace, self.owner, date=day, kind=kind, reference="SYN-FINANCE",
            narration="Synthetic finance activity", submission_key=uuid4(),
            lines=[(self.ledgers[code], side, D(amount)) for code, side, amount in lines],
        )

    def test_posted_cash_flows_inventory_and_working_capital_reconcile(self):
        result = financial_overview(self.workspace, self.owner, self.start, self.end)
        cash = result["cash"]
        self.assertEqual((cash["opening"], cash["opening_adjustments"], cash["closing"]), (0, 100, 195))
        self.assertEqual([row["net"] for row in cash["flows"]], [70, -20, 30, 15])
        self.assertEqual(cash["unclassified"], 1)
        self.assertEqual((result["income"], result["expenses"], result["statements"]["net_result"]), (87, 10, 77))
        self.assertEqual(result["statements"]["difference"], 0)
        self.assertEqual(result["working_capital"]["net"], 195)
        self.assertTrue(result["stock"].reconciled)
        short = financial_overview(self.workspace, self.owner, self.end, self.end)
        self.assertEqual((short["cash"]["opening"], short["cash"]["opening_adjustments"]), (100, 0))

    def test_owner_screen_validates_year_and_displays_cash_comparison(self):
        url = reverse("accounting:finance")
        self.client.force_login(self.owner)
        result = self.client.get(url, {"start": self.start, "end": self.end, "comparison": "previous"})
        self.assertContains(result, "Finance dashboard")
        self.assertContains(result, "Period comparison")
        self.assertContains(result, "₹195.00")
        self.assertIn("no-store", result.headers["Cache-Control"])
        self.assertContains(self.client.get(url, {"year": self.year.pk}), "Cash flow")
        self.assertContains(self.client.get(url, {"year": self.foreign_year.pk}), "Select a valid choice.")
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(url).status_code, 403)
