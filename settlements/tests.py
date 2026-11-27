from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from accounting.models import Journal, Ledger
from accounting.services import post_journal, setup_books

from dashboard.models import Customer, TeamMembership
from invoicing.issuance import cancel_internal_invoice, issue_internal_purchase, issue_internal_sale
from invoicing.returns import record_invoice_return
from invoicing.test_data import InvoiceFixture

from .allocations import record_payment_allocation
from .balances import active_payments, ageing_bucket, invoice_balances, unallocated_payments
from .models import PartyPayment, PaymentAllocation
from .services import record_party_payment, set_invoice_due_date
from .terms import apply_credit_due_date, customer_credit_exposure, record_mse_deadline, save_credit_profile


@override_settings(INTERNAL_INVOICE_ISSUANCE=True)
class InvoiceBalanceTests(InvoiceFixture, TestCase):
    def sale(self):
        draft = self.draft(self.dispatch)
        _, inputs = self.issue_inputs(draft)
        return issue_internal_sale(self.workspace, self.owner, **inputs)

    def test_due_date_and_boundary_buckets(self):
        invoice = self.sale()
        due = date(2026, 5, 15)
        for offset, bucket in ((-1, "Current"), (0, "Current"), (1, "1–30"), (30, "1–30"), (31, "31–60"),
                               (60, "31–60"), (61, "61–90"), (90, "61–90"), (91, "Over 90")):
            with self.subTest(offset=offset):
                self.assertEqual(ageing_bucket(due, due + timedelta(days=offset)), bucket)
        self.assertEqual(invoice_balances(self.workspace, due)[0].bucket, "No due date")
        terms = set_invoice_due_date(self.workspace, self.owner, invoice_id=invoice.pk, due_on=due)
        self.assertEqual(set_invoice_due_date(self.workspace, self.owner, invoice_id=invoice.pk, due_on=due), terms)
        with self.assertRaisesMessage(ValidationError, "already recorded"):
            set_invoice_due_date(self.workspace, self.owner, invoice_id=invoice.pk, due_on=due + timedelta(days=1))
        with self.assertRaises(PermissionDenied):
            set_invoice_due_date(self.workspace, self.other, invoice_id=invoice.pk, due_on=due)
        with self.assertRaises(ValidationError):
            set_invoice_due_date(self.other_workspace, self.other, invoice_id=invoice.pk, due_on=due)
        row, = invoice_balances(self.workspace, due + timedelta(days=1))
        self.assertEqual((row.bucket, row.adjusted_total), ("1–30", Decimal("336.00")))
        self.assertEqual(invoice_balances(self.other_workspace, due), [])

    def test_returns_and_cancellations_affect_only_reports_after_posting(self):
        sale = self.sale()
        opening = sale.posting_on
        earlier = opening - timedelta(days=1)
        later = date(2026, 6, 1)
        record_invoice_return(self.workspace, self.owner, invoice_id=sale.pk, posting_on=later,
                              quantity=Decimal("1"), reason="Synthetic return", submission_key=uuid4())
        draft = self.draft(self.receipt, purchase_unit_price=Decimal("75"), supplier_invoice_date=opening)
        purchase = issue_internal_purchase(self.workspace, self.owner, **self.purchase_issue_inputs(draft))
        cancel_internal_invoice(self.workspace, self.owner, invoice_id=purchase.pk, posting_on=later,
                                reason="Synthetic cancellation")
        self.assertEqual(invoice_balances(self.workspace, earlier), [])
        prior = {row.invoice.pk: row.adjusted_total for row in invoice_balances(self.workspace, opening)}
        self.assertEqual(prior, {sale.pk: Decimal("336.00"), purchase.pk: Decimal("420.00")})
        after = {row.invoice.pk: row.adjusted_total for row in invoice_balances(self.workspace, later)}
        self.assertEqual(after, {sale.pk: Decimal("224.00"), purchase.pk: Decimal("0.00")})

    def test_purchase_due_date_can_precede_later_posting(self):
        invoice_date = date(2026, 4, 20)
        draft = self.draft(self.receipt, purchase_unit_price=Decimal("75"), supplier_invoice_date=invoice_date)
        values = self.purchase_issue_inputs(draft) | {"supplier_invoice_date": invoice_date}
        invoice = issue_internal_purchase(self.workspace, self.owner, **values)
        with self.assertRaisesMessage(ValidationError, "cannot precede the invoice date"):
            set_invoice_due_date(self.workspace, self.owner, invoice_id=invoice.pk, due_on=date(2026, 4, 19))
        terms = set_invoice_due_date(self.workspace, self.owner, invoice_id=invoice.pk, due_on=date(2026, 4, 30))
        self.assertLess(terms.due_on, invoice.posting_on)


class SettlementFixture(InvoiceFixture):
    def payment_values(self, receipt=True):
        setup_books(self.workspace, self.owner, 2026)
        ids = dict(Ledger.objects.filter(workspace=self.workspace).values_list("code", "pk"))
        return {
            "posting_on": date(2026, 5, 1), "amount": Decimal("150.25"),
            "funds_ledger_id": ids["1010"], "control_ledger_id": ids["1100" if receipt else "2000"],
            "submission_key": uuid4(), "external_reference": " demo/100 ", "narration": "Synthetic settlement",
            **({"customer_id": self.order.customer_id} if receipt else {"supplier_id": self.receipt.purchase_order.supplier_id}),
        }


class PartyPaymentTests(SettlementFixture, TestCase):
    def test_customer_receipt_is_sealed_immutable_and_idempotent(self):
        values = self.payment_values()
        payment = record_party_payment(self.workspace, self.owner, **values)
        self.assertEqual(payment.external_reference, "DEMO/100")
        self.assertTrue(payment.journal.sealed)
        self.assertEqual(payment.journal.kind, Journal.Kind.RECEIPT)
        self.assertEqual(list(payment.journal.lines.values_list("ledger__code", "side", "amount")), [
            ("1010", "D", Decimal("150.25")), ("1100", "C", Decimal("150.25")),
        ])
        self.assertEqual(record_party_payment(self.workspace, self.owner, **values), payment)
        with self.assertRaisesMessage(ValidationError, "different payment"):
            record_party_payment(self.workspace, self.owner, **(values | {"amount": Decimal("150.26")}))
        with self.assertRaisesMessage(ValidationError, "already recorded"):
            record_party_payment(self.workspace, self.owner, **(values | {"submission_key": uuid4()}))
        with self.assertRaises(IntegrityError), transaction.atomic():
            PartyPayment.objects.filter(pk=payment.pk).update(amount=Decimal("1"))
        self.assertEqual(Journal.objects.count(), 1)

    def test_supplier_payment_reversal_changes_visibility_on_reversal_date(self):
        values = self.payment_values(receipt=False)
        payment = record_party_payment(self.workspace, self.owner, **values)
        self.assertEqual(payment.journal.kind, Journal.Kind.PAYMENT)
        self.assertEqual(list(payment.journal.lines.values_list("ledger__code", "side", "amount")), [
            ("2000", "D", Decimal("150.25")), ("1010", "C", Decimal("150.25")),
        ])
        day = date(2026, 6, 1)
        post_journal(self.workspace, self.owner, date=day, kind=Journal.Kind.REVERSAL,
                     reference="SYN-REVERSED", narration="Synthetic reversal", submission_key=uuid4(),
                     reverses=payment.journal)
        self.assertEqual(list(active_payments(self.workspace, values["posting_on"])), [payment])
        self.assertFalse(active_payments(self.workspace, day).exists())
        self.assertFalse(active_payments(self.other_workspace, values["posting_on"]).exists())

    def test_receipt_enforces_scope_and_rolls_back_if_attachment_fails(self):
        values = self.payment_values()
        with self.assertRaises(PermissionDenied):
            record_party_payment(self.workspace, self.other, **values)
        with self.assertRaises(ValidationError):
            record_party_payment(self.other_workspace, self.other, **values)
        with self.assertRaises(ValidationError):
            record_party_payment(self.workspace, self.owner, **(values | {"control_ledger_id": values["funds_ledger_id"]}))
        with patch("settlements.services.PartyPayment.objects.create", side_effect=IntegrityError):
            with self.assertRaises(IntegrityError):
                record_party_payment(self.workspace, self.owner, **values)
        self.assertFalse(Journal.objects.exists())
        self.assertFalse(PartyPayment.objects.exists())


@override_settings(INTERNAL_INVOICE_ISSUANCE=True)
class PaymentAllocationTests(SettlementFixture, TestCase):
    def setup_receivable(self, amount):
        values = self.payment_values() | {"amount": Decimal(amount), "posting_on": date(2026, 4, 20)}
        payment = record_party_payment(self.workspace, self.owner, **values)
        draft = self.draft(self.dispatch)
        _, issue = self.issue_inputs(draft)
        invoice = issue_internal_sale(self.workspace, self.owner, **issue)
        return invoice, payment

    def allocate(self, invoice, payment, amount, **overrides):
        values = {"invoice_id": invoice.pk, "payment_id": payment.pk, "posted_on": invoice.posting_on,
                  "amount": Decimal(amount), "submission_key": uuid4()}
        return record_payment_allocation(self.workspace, self.owner, **(values | overrides))

    def test_advance_partial_and_excess_receipt_remain_separate_from_invoice_balance(self):
        invoice, payment = self.setup_receivable("500")
        day = invoice.posting_on
        key = uuid4()
        self.assertEqual(unallocated_payments(self.workspace, payment.journal.date), [(payment, Decimal("500"))])
        entry = self.allocate(invoice, payment, "200", submission_key=key)
        self.assertEqual(self.allocate(invoice, payment, "200", submission_key=key), entry)
        row, = invoice_balances(self.workspace, day)
        self.assertEqual((row.allocated, row.outstanding), (Decimal("200"), Decimal("136")))
        with self.assertRaisesMessage(ValidationError, "invoice balance"):
            self.allocate(invoice, payment, "137")
        self.allocate(invoice, payment, "136")
        self.assertEqual(invoice_balances(self.workspace, day)[0].outstanding, Decimal("0"))
        self.assertEqual(unallocated_payments(self.workspace, day), [(payment, Decimal("164"))])
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentAllocation.objects.filter(pk=entry.pk).update(amount="1")
        self.assertEqual(Journal.objects.count(), 2)

    def test_return_creates_invoice_credit_until_explicit_allocation_adjustment(self):
        invoice, payment = self.setup_receivable("336")
        day = date(2026, 6, 1)
        original = self.allocate(invoice, payment, "336")
        record_invoice_return(self.workspace, self.owner, invoice_id=invoice.pk, posting_on=day,
                              quantity=Decimal("1"), reason="Synthetic return", submission_key=uuid4())
        self.assertEqual(invoice_balances(self.workspace, day)[0].outstanding, Decimal("-112"))
        self.assertEqual(unallocated_payments(self.workspace, day)[0][1], Decimal("0"))
        self.allocate(invoice, payment, "112", reverses_id=original.pk, posted_on=day, reason="Transfer credit")
        self.assertEqual(invoice_balances(self.workspace, day)[0].outstanding, Decimal("0"))
        self.assertEqual(unallocated_payments(self.workspace, day)[0][1], Decimal("112"))
        with self.assertRaisesMessage(ValidationError, "original allocation"):
            self.allocate(invoice, payment, "225", reverses_id=original.pk, posted_on=day, reason="Too large")
        self.assertEqual(invoice_balances(self.workspace, invoice.posting_on)[0].outstanding, Decimal("0"))

    def test_payment_reversal_reopens_invoice_on_its_posting_date(self):
        invoice, payment = self.setup_receivable("336")
        date_reversed = date(2026, 6, 1)
        self.allocate(invoice, payment, "100")
        post_journal(self.workspace, self.owner, date=date_reversed, kind=Journal.Kind.REVERSAL,
                     reference="REVERSED", narration="Synthetic payment reversal", submission_key=uuid4(),
                     reverses=payment.journal)
        self.assertEqual(invoice_balances(self.workspace, invoice.posting_on)[0].outstanding, Decimal("236"))
        self.assertEqual(invoice_balances(self.workspace, date_reversed)[0].outstanding, Decimal("336"))
        self.assertEqual(unallocated_payments(self.workspace, date_reversed), [])
        with self.assertRaisesMessage(ValidationError, "not available"):
            self.allocate(invoice, payment, "1", posted_on=date_reversed)

    def test_rejects_other_party_and_checks_supplier_allocations(self):
        invoice, _ = self.setup_receivable("336")
        values = self.payment_values(receipt=False) | {"external_reference": "SUP-X"}
        payment = record_party_payment(self.workspace, self.owner, **values)
        with self.assertRaisesMessage(ValidationError, "same party"):
            self.allocate(invoice, payment, "10")
        day = self.receipt.date
        draft = self.draft(self.receipt, purchase_unit_price=Decimal("75"), supplier_invoice_date=day)
        purchase = issue_internal_purchase(self.workspace, self.owner, **self.purchase_issue_inputs(draft))
        self.allocate(purchase, payment, "120")
        row, = invoice_balances(self.workspace, day, invoice_id=purchase.pk)
        self.assertEqual(row.outstanding, Decimal("300"))
        with self.assertRaises(PermissionDenied):
            record_payment_allocation(self.workspace, self.other, invoice_id=purchase.pk, payment_id=payment.pk,
                                      posted_on=day, amount=Decimal("1"), submission_key=uuid4())
        self.assertEqual(invoice_balances(self.other_workspace, day), [])


@override_settings(INTERNAL_INVOICE_ISSUANCE=True)
class CreditTermsTests(InvoiceFixture, TestCase):
    def test_credit_defaults_and_advisory_use_posted_exposure(self):
        customer_id = self.order.customer_id
        save_credit_profile(self.workspace, self.owner, customer_id=customer_id,
                            credit_days=15, credit_limit=Decimal("400"))
        draft = self.draft(self.dispatch)
        _, issue = self.issue_inputs(draft)
        invoice = issue_internal_sale(self.workspace, self.owner, **issue)
        due = apply_credit_due_date(self.workspace, self.owner, invoice_id=invoice.pk)
        self.assertEqual(due.due_on, invoice.posting_on + timedelta(days=15))
        warning = customer_credit_exposure(self.workspace, customer_id=customer_id, proposed_total=Decimal("100"),
                                           as_of=due.due_on + timedelta(days=1))
        self.assertEqual((warning.posted_due, warning.overdue, warning.projected),
                         (Decimal("336"), Decimal("336"), Decimal("436")))
        self.assertTrue(warning.exceeds_limit)
        self.assertFalse(customer_credit_exposure(
            self.other_workspace, customer_id=customer_id, proposed_total=Decimal("100"), as_of=due.due_on,
        ).exceeds_limit)
        with self.assertRaises(ValidationError):
            save_credit_profile(self.other_workspace, self.other, customer_id=customer_id, credit_days=30)
        with self.assertRaises(PermissionDenied):
            save_credit_profile(self.workspace, self.other, customer_id=customer_id, credit_days=30)

    def purchase(self):
        day = self.receipt.date
        draft = self.draft(self.receipt, purchase_unit_price=Decimal("75"), supplier_invoice_date=day)
        return issue_internal_purchase(self.workspace, self.owner, **self.purchase_issue_inputs(draft))

    def test_mse_deadline_requires_review_and_uses_fifteen_days_without_written_terms(self):
        invoice = self.purchase()
        accepted = self.receipt.date + timedelta(days=3)
        values = {"invoice_id": invoice.pk, "accepted_on": accepted,
                  "evidence_reference": "Synthetic documented acceptance", "eligibility_reviewed": True}
        with self.assertRaisesMessage(ValidationError, "eligibility"):
            record_mse_deadline(self.workspace, self.owner, **(values | {"eligibility_reviewed": False}))
        with self.assertRaises(ValidationError):
            record_mse_deadline(self.other_workspace, self.other, **values)
        result = record_mse_deadline(self.workspace, self.owner, **values)
        self.assertEqual(result.deadline, accepted + timedelta(days=15))
        self.assertEqual(record_mse_deadline(self.workspace, self.owner, **values), result)
        self.assertIsNone(invoice.__class__.objects.get(pk=invoice.pk).mse_deadline.written_due_on)

    def test_reviewed_written_terms_are_capped_at_forty_five_days(self):
        invoice = self.purchase()
        accepted = self.receipt.date
        written = accepted + timedelta(days=70)
        result = record_mse_deadline(
            self.workspace, self.owner, invoice_id=invoice.pk, eligibility_reviewed=True,
            accepted_on=accepted, written_due_on=written, evidence_reference="Synthetic written terms",
        )
        self.assertEqual((result.written_due_on, result.deadline), (written, accepted + timedelta(days=45)))


@override_settings(INTERNAL_INVOICE_ISSUANCE=True)
class SettlementStatementTests(SettlementFixture, TestCase):
    def setUp(self):
        self.client.force_login(self.owner)

    def statement_invoice(self):
        draft = self.draft(self.dispatch)
        _, issue = self.issue_inputs(draft)
        return issue_internal_sale(self.workspace, self.owner, **issue)

    def test_statement_reports_allocations_due_dates_and_unassigned_advance(self):
        invoice = self.statement_invoice()
        payment = record_party_payment(self.workspace, self.owner, **(self.payment_values() | {"amount": Decimal("250")}))
        due = invoice.posting_on + timedelta(days=1)
        set_invoice_due_date(self.workspace, self.owner, invoice_id=invoice.pk, due_on=due)
        record_payment_allocation(self.workspace, self.owner, invoice_id=invoice.pk, payment_id=payment.pk,
                                  posted_on=due, amount=Decimal("100"), submission_key=uuid4())
        url = reverse("accounting:settlements:statement")
        response = self.client.get(url, {"as_of": (due + timedelta(days=1)).isoformat(), "customer": self.order.customer_id})
        self.assertContains(response, "Ageing")
        self.assertContains(response, "236.00")
        self.assertContains(response, "150.00")
        self.assertContains(response, "DEMO/100")
        self.assertIn("no-store", response.headers["Cache-Control"])
        empty = self.client.get(url, {"as_of": (invoice.posting_on - timedelta(days=1)).isoformat()})
        self.assertNotContains(empty, invoice.number)
        self.assertEqual(self.client.post(url).status_code, 405)

    def test_reminder_is_manual_and_uses_current_outstanding(self):
        invoice = self.statement_invoice()
        Customer.objects.filter(pk=self.order.customer_id).update(phone="+12025550101")
        url = reverse("accounting:settlements:reminder", args=[invoice.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        set_invoice_due_date(self.workspace, self.owner, invoice_id=invoice.pk, due_on=invoice.posting_on)
        response = self.client.get(url)
        self.assertContains(response, f"INR 336.00 due on invoice {invoice.number}")
        self.assertContains(response, "https://wa.me/12025550101?text=")
        self.assertContains(response, 'rel="noopener noreferrer"')
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(self.client.post(url).status_code, 405)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_statements_enforce_owner_gate_and_company_filter(self):
        invoice = self.statement_invoice()
        url = reverse("accounting:settlements:statement")
        with self.settings(INTERNAL_INVOICE_ISSUANCE=False):
            self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(url), invoice.number)
        self.assertNotContains(self.client.get(url, {"customer": self.order.customer_id}), invoice.number)
        staff = type(self.owner).objects.create_user(username="settlement-team")
        TeamMembership.objects.create(account=self.workspace, user=staff, role=TeamMembership.Role.MANAGER)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(url).status_code, 403)
