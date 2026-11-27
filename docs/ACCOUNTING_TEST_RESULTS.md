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

## Overnight Checkpoint 04, partial

- 04A: Four GST calculator, rate and format tests passed. Full runs passed 135 tests in 132.120 seconds and 132.417 seconds.
- 04B: Seven focused tests passed after correcting a synthetic quote fixture. Tests cover sales and purchase snapshots, effective GST component amounts, cross-company inputs, replay rejection and no ledger posting.
- 04B full run 1 passed 138 in 133.842 seconds. Reverse full run 2 passed 138 in 134.857 seconds.
- Django and migration drift checks passed after both slices. These runs used synthetic SQLite test databases. The draft service has no browser workflow and PostgreSQL has not been executed.

- 04C: Nine focused invoicing tests passed, including owner GST registration/rate creation, validation, duplicate rejection, tenant boundaries, manager denial, CSRF and no-store headers.
- 04C full run 1 passed 140 tests in 132.872 seconds. Reverse run 2 passed 140 tests in 133.848 seconds. Django and migration checks passed. Native Chrome verified registration submission and the layout at a 390 px viewport.

- 04D: 17 invoicing and order tests passed, including sales/purchase draft preparation and preview, replay, workspace and manager denial, CSRF and no ledger writes. The first targeted run had an assertion mismatch on Django's invalid-choice message. The corrected test checks the error code. Django and migration checks passed. Full run 1 passed 142 tests in 84.230 seconds. Reverse run 2 passed 142 tests in 84.471 seconds. Chrome verified native sales and purchase draft creation at desktop and phone widths.

- 04E: 14 focused invoicing tests passed. Full normal and reverse runs passed 145 tests in 80.401 and 80.720 seconds.
- 04F: 31 focused invoicing and accounting tests passed. Django and migration checks passed. Full run 1 passed 146 in 81.715 seconds. Reverse run 2 passed 146 in 81.984 seconds.

- The purchase mapping follow-up at `50f785ecd64e93a64853900afb90f0e9fa4575a8` passed 32 focused tests and both 147-test regressions (80.751 seconds normal, 80.623 seconds reverse). The follow-up tested missing or misclassified input-tax ledgers and the different recoverable-tax and cost allocations. Runtime code and migrations were unchanged by this follow-up.

- 04G: 37 invoicing and accounting tests passed. Full runs passed 152 each in 80.726 and 80.427 seconds. Django and migration drift checks passed. Two concurrent SQLite issue requests returned one issued invoice and one sealed journal on a disposable file-backed database. Verified snapshot immutability, execution rollback, sequence reuse after rollback, ordinary journal link rejection, default gating and replay after closing its period.

- 04H: 40 focused tests passed. Normal/reverse full runs passed 155 tests in 87.681 and 86.535 seconds. Django and migration checks passed. The populated SQLite upgrade retained an issued sale and its guard, and downgrade was prevented with purchase evidence present. Native Chrome verified actual purchase price/date entry and mobile preview.

- 04I: 42 focused tests passed. Normal/reverse runs passed 157 tests in 82.196 and 82.173 seconds. Django and migration checks passed. Tests include correction in a later open period, exact inverted lines, immutable records, retries, ownership and rollback.

- 04J: 45 invoicing/accounting tests passed. Full normal/reverse runs passed 160 in 82.130 and 82.249 seconds. Django and migration checks passed. Split sales returns invert the original ledger to the paise. Purchase returns, over-quantity, replay, cancellation conflicts and rollback were tested. A file-backed SQLite probe accepted only one of two concurrent competing returns.
