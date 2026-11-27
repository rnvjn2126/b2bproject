from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from accounting.models import Journal, Ledger
from accounting.services import post_journal, setup_books

from invoicing.issuance import cancel_internal_invoice, issue_internal_purchase, issue_internal_sale
from invoicing.returns import record_invoice_return
from invoicing.test_data import InvoiceFixture

from .balances import active_payments, ageing_bucket, invoice_balances
from .models import PartyPayment
from .services import record_party_payment, set_invoice_due_date


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


class PartyPaymentTests(InvoiceFixture, TestCase):
    def payment_values(self, receipt=True):
        setup_books(self.workspace, self.owner, 2026)
        ids = dict(Ledger.objects.filter(workspace=self.workspace).values_list("code", "pk"))
        return {
            "posting_on": date(2026, 5, 1), "amount": Decimal("150.25"),
            "funds_ledger_id": ids["1010"], "control_ledger_id": ids["1100" if receipt else "2000"],
            "submission_key": uuid4(), "external_reference": " demo/100 ", "narration": "Synthetic settlement",
            **({"customer_id": self.order.customer_id} if receipt else {"supplier_id": self.receipt.purchase_order.supplier_id}),
        }

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
