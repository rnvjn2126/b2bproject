# Accounting test results

## Phase 1, 27 November 2026

- Django system check passed. Migration drift check reported no changes.
- All seven focused accounting tests passed. The complete project suite passed all 116 tests.
- Two concurrent submissions in separate database connections on file-backed SQLite returned the same journal ID. The database contained one journal and two lines.
- Chrome with synthetic data verified native sign-in, financial year setup, dynamic journal row creation, posting, and trial balance at a 390 px viewport.
- PostgreSQL concurrency and the full financial month simulation with GST, inventory and bank reconciliation remain open. Existing validations were exercised on SQLite.
