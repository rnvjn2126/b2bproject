from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook

from accounting.models import Journal, Ledger
from accounting.services import post_journal, setup_books
from dashboard.models import BusinessAccount, Customer
from settlements.services import record_party_payment

from .instruments import record_cheque_event, record_instrument
from .models import ChequeEvent, ReportedInstrument, StatementBatch, StatementLine, StatementMatch
from .reconciliation import confirm_match, suggest_matches, unmatched_report
from .services import funds_book, register_funds_account, transfer_funds
from .statements import import_statement, preview_statement


class BankingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.owner = users.create_user(username="bank-owner")
        cls.other = users.create_user(username="bank-other")
        cls.workspace = BusinessAccount.objects.create(owner=cls.owner, name="Synthetic Treasury")
        cls.other_workspace = BusinessAccount.objects.create(owner=cls.other, name="Other Synthetic Treasury")
        setup_books(cls.workspace, cls.owner, 2026)
        cls.bank_ledger = Ledger.objects.get(workspace=cls.workspace, code="1010")
        cls.cash_ledger = Ledger.objects.get(workspace=cls.workspace, code="1000")
        cls.petty_ledger = Ledger.objects.create(workspace=cls.workspace, code="1020", name="Petty cash",
                                                group=cls.cash_ledger.group)
        cls.bank = register_funds_account(cls.workspace, cls.owner, ledger_id=cls.bank_ledger.pk,
                                          name="Synthetic bank", kind="bank", last_four="0123")
        cls.cash = register_funds_account(cls.workspace, cls.owner, ledger_id=cls.cash_ledger.pk,
                                          name="Cash counter", kind="cash")
        cls.petty = register_funds_account(cls.workspace, cls.owner, ledger_id=cls.petty_ledger.pk,
                                           name="Petty cash counter", kind="petty")

    def test_transfers_and_date_filtered_books_reconcile(self):
        first, second = date(2026, 5, 1), date(2026, 5, 10)
        equity = Ledger.objects.get(workspace=self.workspace, code="3000")
        post_journal(self.workspace, self.owner, date=first, kind=Journal.Kind.OPENING, reference="SYN-OPEN",
                     narration="Synthetic capital", submission_key=uuid4(),
                     lines=((self.bank_ledger, "D", Decimal("1000")), (equity, "C", Decimal("1000"))))
        data = {"from_id": self.bank.pk, "to_id": self.petty.pk, "posting_on": second, "amount": Decimal("300.15"),
                "submission_key": uuid4(), "reference": "SYN-TRANSFER"}
        transfer = transfer_funds(self.workspace, self.owner, **data)
        self.assertTrue(transfer.sealed)
        self.assertEqual(transfer_funds(self.workspace, self.owner, **data), transfer)
        with self.assertRaises(ValidationError):
            transfer_funds(self.workspace, self.owner, **(data | {"amount": Decimal("301")}))
        bank = funds_book(self.workspace, account_id=self.bank.pk, start_on=second, end_on=second)
        petty = funds_book(self.workspace, account_id=self.petty.pk, start_on=first, end_on=second)
        self.assertEqual((bank.opening, bank.rows[0][1], bank.closing, petty.closing),
                         (Decimal("1000"), Decimal("699.85"), Decimal("699.85"), Decimal("300.15")))
        self.assertEqual(bank.closing + petty.closing, Decimal("1000.00"))

    def test_new_funds_account_is_available_to_existing_party_receipt_service(self):
        customer = Customer.objects.create(owner=self.owner, name="Synthetic Funds Customer")
        control = Ledger.objects.get(workspace=self.workspace, code="1100")
        day = date(2026, 5, 1)
        payment = record_party_payment(
            self.workspace, self.owner, posting_on=day, amount=Decimal("75"), funds_ledger_id=self.petty_ledger.pk,
            control_ledger_id=control.pk, customer_id=customer.pk, submission_key=uuid4(),
        )
        self.assertEqual(payment.journal.kind, Journal.Kind.RECEIPT)
        result = funds_book(self.workspace, account_id=self.petty.pk, start_on=day, end_on=day)
        self.assertEqual(result.closing, Decimal("75"))

    def test_account_and_transfer_scope_and_masking(self):
        self.assertEqual(str(self.bank), "Synthetic bank · •••• 0123")
        with self.assertRaises(PermissionDenied):
            register_funds_account(self.workspace, self.other, ledger_id=self.bank_ledger.pk,
                                   name="Synthetic bank", kind="bank")
        with self.assertRaises(ValidationError):
            register_funds_account(self.workspace, self.owner, ledger_id=self.bank_ledger.pk,
                                   name="Synthetic bank", kind="bank", last_four="12345678")
        with self.assertRaises(ValidationError):
            transfer_funds(self.other_workspace, self.other, from_id=self.bank.pk, to_id=self.cash.pk,
                           posting_on=date(2026, 5, 1), amount=Decimal("10"), submission_key=uuid4())
        with self.assertRaises(ValidationError):
            funds_book(self.other_workspace, account_id=self.bank.pk, start_on=date(2026, 5, 1), end_on=date(2026, 6, 1))
        self.assertFalse(Journal.objects.exists())


    def reported(self, method, **overrides):
        values = {"account_id": self.bank.pk, "method": method, "direction": "in", "reference": " synthetic-ref ",
                  "reported_on": date(2026, 5, 1), "amount": Decimal("10")}
        return record_instrument(self.workspace, self.owner, **(values | overrides))

    def test_electronic_references_do_not_create_or_verify_payments(self):
        for method in ("upi", "neft", "rtgs", "imps"):
            with self.subTest(method=method):
                entry = self.reported(method)
                self.assertEqual(entry.reference, "SYNTHETIC-REF")
                self.assertIsNone(entry.journal_line_id)
                self.assertEqual(self.reported(method), entry)
                with self.assertRaises(ValidationError):
                    self.reported(method, amount=Decimal("11"))
        self.assertEqual(ReportedInstrument.objects.count(), 4)
        self.assertFalse(Journal.objects.exists())

    def test_reported_reference_can_only_link_to_a_matching_posted_bank_line(self):
        journal = transfer_funds(self.workspace, self.owner, from_id=self.cash.pk, to_id=self.bank.pk,
                                 posting_on=date(2026, 5, 1), amount=Decimal("10"), submission_key=uuid4())
        credit = journal.lines.get(side="C")
        debit = journal.lines.get(side="D")
        with self.assertRaises(ValidationError):
            self.reported("neft", journal_line_id=credit.pk)
        self.assertEqual(self.reported("neft", journal_line_id=debit.pk).journal_line_id, debit.pk)
        with self.assertRaises(ValidationError):
            self.reported("imps", journal_line_id=debit.pk)
        self.assertEqual(Journal.objects.count(), 1)

    def test_cheque_events_are_ordered_scoped_and_leave_funds_unchanged(self):
        cheque = self.reported("cheque")
        options = {"instrument_id": cheque.pk, "state": "presented", "happened_on": date(2026, 5, 2),
                   "submission_key": uuid4()}
        with self.assertRaises(ValidationError):
            record_cheque_event(self.workspace, self.owner, **(options | {"state": "cleared"}))
        with self.assertRaises(ValidationError):
            record_cheque_event(self.other_workspace, self.other, **options)
        event = record_cheque_event(self.workspace, self.owner, **options)
        self.assertEqual(record_cheque_event(self.workspace, self.owner, **options), event)
        record_cheque_event(self.workspace, self.owner, **(options | {
            "state": "cleared", "happened_on": date(2026, 5, 3), "submission_key": uuid4(),
        }))
        record_cheque_event(self.workspace, self.owner, **(options | {
            "state": "returned", "reason": "Synthetic bank return", "happened_on": date(2026, 5, 4),
            "submission_key": uuid4(),
        }))
        self.assertEqual(list(cheque.cheque_events.values_list("state", flat=True)),
                         [ChequeEvent.State.PRESENTED, ChequeEvent.State.CLEARED, ChequeEvent.State.RETURNED])
        self.assertFalse(Journal.objects.exists())


    def statement_csv(self, *rows):
        header = "date,reference,description,debit,credit"
        return chr(10).join((header, *rows)).encode("utf-8")

    def test_statement_preview_is_read_only_and_commit_detects_overlap_and_replay(self):
        initial = self.statement_csv("2026-05-01,R1,Synthetic deposit,,250.01",
                                     "2026-05-02,R2,Synthetic withdrawal,30.00,")
        args = {"account_id": self.bank.pk, "content": initial}
        preview = preview_statement(self.workspace, self.owner, **args)
        self.assertEqual([(line.direction, line.amount) for line in preview.new],
                         [("in", Decimal("250.01")), ("out", Decimal("30.00"))])
        self.assertFalse(StatementLine.objects.exists())
        batch = import_statement(self.workspace, self.owner, **args, preview_digest=preview.digest)
        self.assertEqual(import_statement(self.workspace, self.owner, **args, preview_digest=preview.digest), batch)
        self.assertEqual((batch.imported_rows, batch.duplicate_rows), (2, 0))

        overlap = self.statement_csv("2026-05-02,r2,Updated synthetic description,30,",
                                     "2026-05-03,R3,Synthetic other,,10.50")
        options = args | {"content": overlap}
        updated = preview_statement(self.workspace, self.owner, **options)
        self.assertEqual((len(updated.new), len(updated.duplicates)), (1, 1))
        with self.assertRaisesMessage(ValidationError, "overlaps"):
            import_statement(self.workspace, self.owner, **options, preview_digest=updated.digest)
        with self.assertRaisesMessage(ValidationError, "file changed"):
            import_statement(self.workspace, self.owner, **options, preview_digest=preview.digest, skip_known=True)
        next_batch = import_statement(self.workspace, self.owner, **options, preview_digest=updated.digest, skip_known=True)
        self.assertEqual((next_batch.imported_rows, next_batch.duplicate_rows), (1, 1))
        self.assertEqual(StatementLine.objects.count(), 3)
        self.assertFalse(Journal.objects.exists())

    def test_statement_preview_rejects_malformed_ambiguous_and_foreign_inputs(self):
        duplicate = "2026-05-01,,Synthetic repeated debit,10.00,"
        for rows in (
            ("2026-05-01,A,B,12,1",), ("not-a-date,A,B,,10",), ("2026-05-01,A,B,,9.001",),
            ("2099-01-01,A,B,,10",), ("2026-05-01,A,B,,0",), (duplicate, duplicate),
        ):
            with self.subTest(rows=rows), self.assertRaises(ValidationError):
                preview_statement(self.workspace, self.owner, account_id=self.bank.pk, content=self.statement_csv(*rows))
        content = self.statement_csv("2026-05-01,R,Synthetic deposit,,1")
        with self.assertRaises(PermissionDenied):
            preview_statement(self.workspace, self.other, account_id=self.bank.pk, content=content)
        with self.assertRaises(ValidationError):
            preview_statement(self.other_workspace, self.other, account_id=self.bank.pk, content=content)
        self.assertFalse(StatementBatch.objects.exists())

    def test_preview_digest_and_overlap_belong_to_selected_account(self):
        content = self.statement_csv("2026-05-01,R,Synthetic deposit,,1")
        prior = preview_statement(self.workspace, self.owner, account_id=self.bank.pk, content=content)
        import_statement(self.workspace, self.owner, account_id=self.bank.pk, content=content, preview_digest=prior.digest)
        ledger = Ledger.objects.create(workspace=self.workspace, code="1011", name="Second synthetic bank",
                                       group=self.bank_ledger.group)
        second = register_funds_account(self.workspace, self.owner, ledger_id=ledger.pk,
                                        name="Second synthetic bank", kind="bank")
        other = preview_statement(self.workspace, self.owner, account_id=second.pk, content=content)
        self.assertNotEqual(other.digest, prior.digest)
        self.assertEqual((len(other.new), len(other.duplicates)), (1, 0))
        with self.assertRaises(ValidationError):
            import_statement(self.workspace, self.owner, account_id=second.pk, content=content, preview_digest=prior.digest)

    def test_statement_rows_and_batch_roll_back_together(self):
        file = self.statement_csv("2026-05-01,R,Synthetic deposit,,1")
        preview = preview_statement(self.workspace, self.owner, account_id=self.bank.pk, content=file)
        with patch("banking.statements.StatementLine.objects.bulk_create", side_effect=IntegrityError):
            with self.assertRaises(IntegrityError):
                import_statement(self.workspace, self.owner, account_id=self.bank.pk, content=file, preview_digest=preview.digest)
        self.assertFalse(StatementBatch.objects.exists())
        self.assertFalse(StatementLine.objects.exists())

    def test_reconciliation_ranks_reference_and_preserves_unmatched_totals(self):
        day = date(2026, 5, 1)
        content = self.statement_csv("2026-05-01,MATCH,Deposit,,10",
                                     "2026-05-02,SECOND,Another deposit,,10",
                                     "2026-05-02,OUT,Withdrawal,3.25,")
        upload = {"account_id": self.bank.pk, "content": content}
        preview = preview_statement(self.workspace, self.owner, **upload)
        batch = import_statement(self.workspace, self.owner, **upload, preview_digest=preview.digest)
        first = batch.lines.get(reference="MATCH")
        second = batch.lines.get(reference="SECOND")

        def transfer(amount, reference, posted_on=day):
            return transfer_funds(self.workspace, self.owner, from_id=self.cash.pk, to_id=self.bank.pk,
                                  posting_on=posted_on, amount=Decimal(amount), reference=reference,
                                  submission_key=uuid4())

        nearby = transfer("10", "DIFFERENT").lines.get(side="D")
        matching = transfer("10", "match", day + timedelta(days=2)).lines.get(side="D")
        wrong_journal = transfer("9", "INVALID")
        self.assertEqual(suggest_matches(self.workspace, self.owner, statement_line_id=first.pk), [matching, nearby])
        for invalid in (wrong_journal.lines.get(side="D"), matching.journal.lines.get(side="C")):
            with self.assertRaisesMessage(ValidationError, "same account, amount and direction"):
                confirm_match(self.workspace, self.owner, statement_line_id=first.pk, journal_line_id=invalid.pk)
        with self.assertRaises(PermissionDenied):
            suggest_matches(self.workspace, self.other, statement_line_id=first.pk)
        with self.assertRaises(ValidationError):
            confirm_match(self.other_workspace, self.other, statement_line_id=first.pk, journal_line_id=matching.pk)
        kwargs = {"statement_line_id": first.pk, "journal_line_id": matching.pk}
        result = confirm_match(self.workspace, self.owner, **kwargs)
        self.assertEqual(result.confirmed_by, self.owner)
        with self.assertRaises(IntegrityError), transaction.atomic():
            StatementMatch.objects.filter(pk=result.pk).update(confirmed_by=self.other)
        with self.assertRaises(IntegrityError), transaction.atomic():
            StatementMatch.objects.create(statement_line=second, journal_line=wrong_journal.lines.get(side="D"),
                                          confirmed_by=self.owner)
        self.assertEqual(confirm_match(self.workspace, self.owner, **kwargs), result)
        self.assertEqual(suggest_matches(self.workspace, self.owner, statement_line_id=first.pk), [])
        with self.assertRaisesMessage(ValidationError, "already reconciled"):
            confirm_match(self.workspace, self.owner, **(kwargs | {"journal_line_id": nearby.pk}))
        with self.assertRaisesMessage(ValidationError, "already reconciled"):
            confirm_match(self.workspace, self.owner, **(kwargs | {"statement_line_id": second.pk}))
        report = unmatched_report(self.workspace, self.owner, account_id=self.bank.pk,
                                  start_on=day, end_on=day + timedelta(days=3))
        self.assertEqual((report.statement_net, report.ledger_net, report.difference),
                         (Decimal("6.75"), Decimal("19"), Decimal("-12.25")))
        self.assertEqual(StatementMatch.objects.count(), 1)
        self.assertEqual(Journal.objects.count(), 3)


    @override_settings(INTERNAL_INVOICE_ISSUANCE=True)
    def test_owner_reconciliation_views_confirm_with_csrf(self):
        day = date(2026, 5, 1)
        upload = {"account_id": self.bank.pk, "content": self.statement_csv("2026-05-01,REF,Deposit,,10")}
        preview = preview_statement(self.workspace, self.owner, **upload)
        batch = import_statement(self.workspace, self.owner, **upload, preview_digest=preview.digest)
        entry = batch.lines.get()
        journal = transfer_funds(self.workspace, self.owner, from_id=self.cash.pk, to_id=self.bank.pk,
                                 posting_on=day, amount=Decimal("10"), reference="REF", submission_key=uuid4())
        line = journal.lines.get(side="D")
        report = reverse("accounting:bank_reconciliation")
        confirm = reverse("accounting:bank_reconciliation_confirm", args=[entry.pk])
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(report, {"account": self.bank.pk, "start_on": day, "end_on": day}),
                            "Review matches")
        self.assertContains(self.client.get(confirm), journal.transaction_reference)
        self.assertFalse(StatementMatch.objects.exists())
        locked = Client(enforce_csrf_checks=True)
        locked.force_login(self.owner)
        self.assertEqual(locked.post(confirm, {"journal_line_id": line.pk}).status_code, 403)
        with self.settings(INTERNAL_INVOICE_ISSUANCE=False):
            self.assertEqual(self.client.get(report).status_code, 404)
        self.assertEqual(self.client.post(confirm, {"journal_line_id": line.pk}).status_code, 302)
        self.assertEqual(StatementMatch.objects.get().journal_line, line)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(confirm).status_code, 404)



    @override_settings(INTERNAL_INVOICE_ISSUANCE=True)
    def test_owner_statement_upload_previews_before_confirmation(self):
        url = reverse("accounting:bank_statement_upload")
        content = self.statement_csv("2026-05-01,REF,Synthetic deposit,,10")

        def upload(data=content):
            return SimpleUploadedFile("synthetic.csv", data, content_type="text/csv")

        self.client.force_login(self.owner)
        response = self.client.post(url, {"action": "preview", "account": self.bank.pk, "statement": upload()})
        self.assertContains(response, "1 new entry")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertFalse(StatementBatch.objects.exists())
        digest = response.context["preview"].digest
        confirmation = {"action": "confirm", "confirm-account": self.bank.pk, "confirm-preview_digest": digest}
        invalid = self.client.post(url, confirmation | {"confirm-statement": upload(content + bytes([10]))})
        self.assertContains(invalid, "The file changed after preview")
        self.assertFalse(StatementBatch.objects.exists())
        accepted = self.client.post(url, confirmation | {"confirm-statement": upload()}, follow=True)
        self.assertContains(accepted, "New entries staged: 1")
        self.assertEqual(StatementLine.objects.get().reference, "REF")
        self.assertFalse(Journal.objects.exists())
        self.client.force_login(self.other)
        self.assertContains(self.client.post(url, {"action": "preview", "account": self.bank.pk,
                                                   "statement": upload()}), "Select a valid choice")
        self.assertEqual(StatementBatch.objects.count(), 1)



    def statement_workbook(self, amount, *, extra_sheet=False):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["date", "reference", "description", "debit", "credit"])
        sheet.append([date(2026, 5, 1), "REF", "Synthetic Excel deposit", None, amount])
        if extra_sheet:
            workbook.create_sheet("Extra")
        buffer = BytesIO()
        workbook.save(buffer)
        workbook.close()
        return buffer.getvalue()

    @override_settings(INTERNAL_INVOICE_ISSUANCE=True)
    def test_statement_workbook_uses_same_preview_and_cross_format_fingerprint(self):
        url = reverse("accounting:bank_statement_upload")
        content = self.statement_workbook(27.35)

        def upload():
            return SimpleUploadedFile("synthetic.xlsx", content)

        self.client.force_login(self.owner)
        response = self.client.post(url, {"action": "preview", "account": self.bank.pk, "statement": upload()})
        self.assertContains(response, "27.35")
        self.assertFalse(StatementLine.objects.exists())
        digest = response.context["preview"].digest
        self.assertEqual(self.client.post(url, {"action": "confirm", "confirm-account": self.bank.pk,
                                                "confirm-preview_digest": digest, "confirm-statement": upload()}).status_code, 302)
        self.assertEqual(StatementLine.objects.get().amount, Decimal("27.35"))
        csv = self.statement_csv("2026-05-01,ref,Another description,,27.35")
        preview = preview_statement(self.workspace, self.owner, account_id=self.bank.pk, content=csv)
        self.assertEqual((len(preview.new), len(preview.duplicates)), (0, 1))
        self.assertFalse(Journal.objects.exists())

    def test_statement_workbook_rejects_formulas_extra_sheets_and_invalid_archives(self):
        for content, message in (
            (self.statement_workbook("=1+2"), "formula or spreadsheet error"),
            (self.statement_workbook(5, extra_sheet=True), "one worksheet"),
            (b"synthetic non-archive", "valid, supported XLSX"),
        ):
            with self.subTest(message=message), self.assertRaisesMessage(ValidationError, message):
                preview_statement(self.workspace, self.owner, account_id=self.bank.pk, content=content, file_format="xlsx")
        self.assertFalse(StatementBatch.objects.exists())

    @override_settings(INTERNAL_INVOICE_ISSUANCE=True)
    def test_owner_can_match_an_older_ledger_entry_by_exact_reference(self):
        content = self.statement_csv("2026-05-19,BANKREF,Synthetic deposit,,10")
        upload = {"account_id": self.bank.pk, "content": content}
        preview = preview_statement(self.workspace, self.owner, **upload)
        entry = import_statement(self.workspace, self.owner, **upload, preview_digest=preview.digest).lines.get()
        journal = transfer_funds(self.workspace, self.owner, from_id=self.cash.pk, to_id=self.bank.pk,
                                 posting_on=date(2026, 5, 1), amount=Decimal("10"), submission_key=uuid4(), reference="SEARCH")
        line = journal.lines.get(side="D")
        self.client.force_login(self.owner)
        url = reverse("accounting:bank_reconciliation_confirm", args=[entry.pk])
        self.assertContains(self.client.get(url), "No available suggested matches")
        url = reverse("accounting:bank_reconciliation_confirm", args=[entry.pk], query={"reference": "search"})
        self.assertContains(self.client.get(url), journal.transaction_reference)
        self.assertEqual(self.client.post(url, {"journal_line_id": line.pk}).status_code, 302)
        self.assertEqual(StatementMatch.objects.get().journal_line, line)
