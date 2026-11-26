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

## Balance sheet and profit and loss, 27 November 2026

- Django system check passed. Migration drift check reported no changes.
- Focused accounting verification passed all 12 tests. New cases cover date ranges, branch and workspace boundaries, report access, exact reconciliation and visible handling of inconsistent ledger data.
- Test run 1: `manage.py test --noinput` passed all 121 tests in 121.388 seconds.
- Test run 2: `manage.py test --noinput --reverse` passed all 121 tests in 121.752 seconds, using a separate synthetic test database.
- Chrome verified that a posted receipt changes reported income and that the balance sheet reconciles at a 390 px viewport.
- These runs verify this checkpoint. The outstanding checklist items remain open.

## Overnight Checkpoint 01

- 14 targeted accounting tests passed. Full run 1 passed 123 tests in 127.419 seconds. Full run 2 passed 123 tests in reverse order in 126.062 seconds.
- Django check and migration drift check passed. A populated synthetic SQLite database upgraded from accounting migration 0002 and retained its journal and lines. Guards rejected edits, deletes and appends affecting posted journals or locked periods.
- Chrome verified a native journal submission, reconciled trial balance and the accounting audit screen. PostgreSQL trigger execution and concurrency remain unverified.

## Overnight Checkpoint 02

- 16 targeted accounting tests passed. Tests cover all eight review voucher types, exact allocations, draft and approval replays, stale revisions, imbalance rejection, isolation and day book output.
- Run 1 passed all 125 tests in 132.136 seconds. Reverse run 2 passed all 125 tests in 131.931 seconds. Django and migration checks passed.
- Chrome verified owner draft entry, explicit approval, and the resulting day book on mobile.

## Overnight Checkpoint 03

- 6 focused order tests passed after correcting an expected text substring. Covered enquiry and accepted quote conversion, snapshots, gross-margin approval, tenant isolation, CSRF, approvals, partial receipts/dispatch and split suppliers.
- Run 1 passed 131 tests in 84.364 seconds. Reverse run 2 passed 131 tests in 84.370 seconds. Configuration and migration drift checks passed.
- Native Chrome verified quote acceptance, conversion, sales approval and mobile detail. Order PDF assertions covered procurement/customer boundaries. Orders and goods movements created no journals.
