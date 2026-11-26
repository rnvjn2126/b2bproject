import uuid
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from dashboard.models import BusinessAccount, Customer, Quote, RFQ, TeamMembership

from .models import Branch, Journal, JournalLine, Ledger
from .services import lock_period, post_journal, setup_books


class AccountingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.owner = users.create_user(username="books-owner")
        cls.outsider = users.create_user(username="other-books-owner")
        cls.workspace = BusinessAccount.objects.create(owner=cls.owner, name="Sample Steel")
        cls.other = BusinessAccount.objects.create(owner=cls.outsider, name="Other Steel")
        cls.year = setup_books(cls.workspace, cls.owner, 2026)
        setup_books(cls.other, cls.outsider, 2026)
        cls.cash = Ledger.objects.get(workspace=cls.workspace, code="1000")
        cls.capital = Ledger.objects.get(workspace=cls.workspace, code="3000")
        cls.freight = Ledger.objects.get(workspace=cls.workspace, code="5100")
        cls.day = date(2026, 4, 20)

    def setUp(self):
        self.client.force_login(self.owner)

    def post(self, **overrides):
        arguments = {
            "date": self.day, "kind": Journal.Kind.GENERAL, "reference": "TEST-1",
            "narration": "Synthetic payment", "submission_key": uuid.uuid4(),
            "lines": [(self.cash, "D", Decimal("1000.01")), (self.capital, "C", Decimal("1000.01"))],
        }
        return post_journal(self.workspace, self.owner, **(arguments | overrides))

    def test_setup_creates_april_to_march_with_no_duplicate_master_data(self):
        count = Ledger.objects.filter(workspace=self.workspace).count()
        self.assertEqual(setup_books(self.workspace, self.owner, 2026), self.year)
        self.assertEqual(self.year.periods.count(), 12)
        self.assertEqual(self.year.periods.first().starts_on, date(2026, 4, 1))
        self.assertEqual(self.year.periods.last().ends_before, date(2027, 4, 1))
        self.assertEqual(Ledger.objects.filter(workspace=self.workspace).count(), count)
        self.assertContains(self.client.get(reverse("accounting:chart")), "Stock-in-hand")

    def test_idempotent_post_and_exact_balance_validation(self):
        key = uuid.uuid4()
        first = self.post(submission_key=key)
        self.assertEqual(self.post(submission_key=key), first)
        with self.assertRaisesMessage(ValidationError, "different journal"):
            self.post(submission_key=key, narration="Different payload")
        with self.assertRaisesMessage(ValidationError, "equal"):
            self.post(lines=[(self.cash, "D", Decimal("1.01")), (self.capital, "C", Decimal("1.00"))])
        with self.assertRaises(ValidationError):
            self.post(lines=[(self.cash, "D", Decimal("1.001")), (self.capital, "C", Decimal("1.001"))])
        self.assertEqual(Journal.objects.count(), 1)
        self.assertEqual(first.lines.count(), 2)

    def test_locked_period_and_reversal_preserve_original(self):
        entry = self.post()
        self.assertEqual(lock_period(self.workspace, self.owner, entry.period_id), 1)
        self.assertEqual(lock_period(self.workspace, self.owner, entry.period_id), 0)
        with self.assertRaisesMessage(ValidationError, "open period"):
            self.post()
        correction = self.post(reverses=entry, date=date(2026, 5, 1))
        self.assertEqual(correction.reverses, entry)
        self.assertEqual(list(correction.lines.values_list("side", "amount")), [("C", Decimal("1000.01")), ("D", Decimal("1000.01"))])
        self.assertEqual(list(entry.lines.values_list("side", flat=True)), ["D", "C"])
        with self.assertRaisesMessage(ValidationError, "already been reversed"):
            self.post(reverses=entry, date=date(2026, 5, 1))

    def test_opening_movements_and_branch_trial_balance_reconcile(self):
        branch = Branch.objects.create(workspace=self.workspace, code="PUN", name="Pune")
        self.post(kind=Journal.Kind.OPENING, date=date(2026, 4, 1), branch=branch)
        self.post(branch=branch, lines=[(self.freight, "D", Decimal("250.10")), (self.cash, "C", Decimal("250.10"))])
        response = self.client.get(reverse("accounting:trial_balance"), {
            "start": "2026-04-02", "end": "2026-04-30", "branch": branch.pk,
        })
        self.assertContains(response, "Trial balance")
        rows = {item["ledger"].code: item for item in response.context["rows"]}
        self.assertEqual(rows["1000"]["opening"], Decimal("1000.01"))
        self.assertEqual(rows["1000"]["closing_debit"], Decimal("749.91"))
        totals = response.context["totals"]
        self.assertEqual(totals["debit"], totals["credit"])
        self.assertEqual(totals["closing_debit"], totals["closing_credit"])
        self.assertContains(response, "start=2026-04-02")
        detail = self.client.get(reverse("accounting:ledger", args=[self.cash.pk]), {
            "start": "2026-04-02", "end": "2026-04-30",
        })
        self.assertEqual(len(detail.context["detail"]), 1)

    def test_workspace_and_role_boundaries(self):
        entry = self.post()
        self.assertEqual(self.client.get(reverse("accounting:journal", args=[entry.pk])).status_code, 200)
        foreign_ledger = Ledger.objects.get(workspace=self.other, code="1000")
        with self.assertRaisesMessage(ValidationError, "ledgers from your workspace"):
            self.post(lines=[(foreign_ledger, "D", Decimal("1")), (self.capital, "C", Decimal("1"))])
        with self.assertRaises(PermissionDenied):
            lock_period(self.workspace, self.outsider, entry.period_id)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse("accounting:journal", args=[entry.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("accounting:close_period", args=[entry.period_id])).status_code, 404)
        manager = get_user_model().objects.create_user(username="sales-manager")
        TeamMembership.objects.create(account=self.workspace, user=manager, role=TeamMembership.Role.MANAGER)
        self.client.force_login(manager)
        self.assertEqual(self.client.get(reverse("accounting:trial_balance")).status_code, 403)
        self.assertEqual(self.client.post(reverse("accounting:journal_create")).status_code, 403)

    def test_normal_journal_form_and_csrf(self):
        url = reverse("accounting:journal_create")
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(url, {}).status_code, 403)
        response = client.get(url)
        data = {
            "date": self.day.isoformat(), "kind": Journal.Kind.GENERAL,
            "narration": "Capital introduced", "submission_key": response.context["form"].initial["submission_key"],
            "lines-TOTAL_FORMS": 2, "lines-INITIAL_FORMS": 0,
            "lines-0-ledger": self.cash.pk, "lines-0-side": "D", "lines-0-amount": "100.25",
            "lines-1-ledger": self.capital.pk, "lines-1-side": "C", "lines-1-amount": "100.25",
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        }
        result = client.post(url, data)
        self.assertEqual(result.status_code, 302, result.context and result.context["form"].errors)
        self.assertEqual(JournalLine.objects.count(), 2)
        self.assertRedirects(client.post(url, data), result.url)
        self.assertEqual(Journal.objects.count(), 1)

    def test_quotation_acceptance_does_not_recognise_revenue(self):
        customer = Customer.objects.create(owner=self.owner, name="Sample Buyer")
        enquiry = RFQ.objects.create(owner=self.owner, customer=customer, received_on=self.day)
        Quote.objects.create(owner=self.owner, rfq=enquiry, number="QT-SAMPLE", status=Quote.Status.ACCEPTED,
                             target_margin_percent=12, minimum_margin_percent=8, maximum_discount_percent=5)
        self.assertFalse(Journal.objects.exists())
