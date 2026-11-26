# Overnight accounting progress

- **Branch:** `ai/accounting-overnight`
- **Baseline:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`
- **Latest implementation commit:** `326c86d374afd18ca29b96a416c65c985a35df35`. Verified with focused, full and browser tests.
- **Active checkpoint:** 04, Invoicing and Indian GST. Checkpoint 04 remains partial.
- **Last verified task:** owner-only internal draft creation and preview from confirmed sales dispatches and purchase receipts. Replay opens the existing draft and writes no journal.
- **Changed files:** accounting routes and navigation, invoicing forms, service, views and tests, three templates under `templates/invoicing/` and accounting documentation.
- **Migrations:** none in 04D. Invoicing migrations 0001 and 0002 have been exercised on disposable SQLite.
- **Latest tests:** 17 invoicing/order tests passed, plus Django and migration drift checks. 04D full runs passed 142 tests in 84.230 seconds (normal) and 84.471 seconds (reverse). Chrome verified both draft types.
- **Known issues and release gates:** the initial targeted 04D run had an assertion mismatch, corrected before the passing targeted run. Statutory review, invoice posting, full-month reconciliation and PostgreSQL execution remain open.
- **Exact next task:** validate exact debit and credit allocations from saved draft snapshots, then design immutable issue records and connect approved GST postings through the shared posting service. Follow with reversals, returns, notes and A4 print. Keep statutory release gated on professional review. Checkpoints 05–14 remain pending.

## Resume on Windows

From PowerShell use the existing virtual environment. Check usage at the start and confirm the branch and worktree before editing.

```powershell
Set-Location -LiteralPath 'C:/Users/Dueolingo/Documents/Codex/2026-11-22/you-are-responsible-for-developing-my/work/steel-quotes-publish'
git status --short --branch
git log -5 --oneline
Get-Content AGENTS.md
Get-Content docs/ACCOUNTING_HANDOFF.md -TotalCount 20
Get-Content docs/checkpoints/04-gst-invoicing.md
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py check
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py makemigrations --check --dry-run
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py test --noinput
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py test --noinput --reverse
```

See the [checkpoint tracker](ACCOUNTING_CHECKPOINTS.md) and [final report](ACCOUNTING_FINAL_REPORT.md) for pending checkpoints 05–14.
