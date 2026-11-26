# Accounting progress

Baseline: Steel Quotes 5b38dca. Feature branch: ai/steel-accounting.

Phase 1 implements an owner-only Accounts section, custom chart records, April–March financial years, monthly locking, Decimal posting with duplicate prevention, reversals, and branch-filtered ledger and trial balance. All development data was synthetic.

Phase 2 has started with receipt, payment and contra vouchers. Each form posts two lines through the journal service and allows a reference, narration, branch and cost centre. This slice uses the starter Cash and Bank ledgers. References are free text; configurable numbering, attachments and approvals are still open. Sales and purchase invoicing, party account allocation, document conversion and immutable issued invoice snapshots follow. Quotation acceptance remains an operational state change.

To preview on a fresh synthetic development database, use the repository's local Django setup and apply the accounting migrations. Sign in as the owner, open **Accounts**, set up a financial year, then choose **Journals** or **Trial balance**. **Journals** links to the three voucher forms. For an existing development database, check its configuration and back it up before migrating.
