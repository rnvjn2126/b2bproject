# Accounting test results

## Phase 1, 27 November 2026

- Django system check passed. Migration drift check reported no changes.
- All seven focused accounting tests passed. The complete project suite passed all 116 tests.
- Two concurrent submissions in separate database connections on file-backed SQLite returned the same journal ID. The database contained one journal and two lines.
- Chrome with synthetic data verified native sign-in, financial year setup, dynamic journal row creation, posting, and trial balance at a 390 px viewport.
- PostgreSQL concurrency and the full financial month simulation with GST, inventory and bank reconciliation remain open. Existing validations were exercised on SQLite.

## Phase 2 cash voucher milestone, 27 November 2026

- Django system check passed. Migration drift check reported no changes.
- All nine focused accounting tests passed. The complete project suite passed all 118 tests.
- Tested receipt, payment and contra line allocations, cash balance, duplicate submissions, cross-company ledger selection and locked periods.
- Chrome verified that submitting a receipt via the native form updates the trial balance in the same synthetic workspace.
- A concurrent receipt and period lock on separate connections to file-backed SQLite left a consistent ledger. PostgreSQL concurrency remains open.
