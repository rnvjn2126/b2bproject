# Overnight accounting progress

- **Branch:** `ai/accounting-overnight`
- **Baseline:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`
- **Latest implementation commit:** `32511cb580d2228c0706ef46c77d209e4ebd7c81`.
- **Active checkpoint:** 05, Receivables, payables and payments. Statutory release work in 04 remains gated separately.
- **Last verified task:** private, disabled-by-default owner workflow for sales/purchase approval, returns and cancellation, with A4 preview.
- **Changed files:** accounting URL registration, invoice forms, posting and draft services, tests, views and templates.
- **Migrations:** none for 04L. Invoicing migrations 0001–0008 verified on disposable SQLite.
- **Latest tests:** 50 focused passed. Both 165-test suites passed (93.157 and 93.034 seconds). Django and migration checks passed. Chrome standalone verified native issue and phone-width cancellation after an initial sign-in timeout.
- **Pending:** statutory workflow and statutory notes, PostgreSQL checks and the independent Checkpoint 05 work.
- **Exact next task:** add contractual due date records and posted-invoice ageing as-of a selected date, with cancellation/return adjustments and company scope. Then add payments, allocations and tested statutory timeline inputs. Update instructions after the next verified slice.


## Resume on Windows

From PowerShell use the existing virtual environment. Check usage at the start and confirm the branch and worktree before editing.

```powershell
Set-Location -LiteralPath 'C:/Users/Dueolingo/Documents/Codex/2026-11-22/you-are-responsible-for-developing-my/work/steel-quotes-publish'
git status --short --branch
git log -5 --oneline
Get-Content AGENTS.md
Get-Content docs/ACCOUNTING_HANDOFF.md -TotalCount 20
Get-Content docs/checkpoints/05-payments.md
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py check
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py makemigrations --check --dry-run
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py test --noinput
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py test --noinput --reverse
```

See the [checkpoint tracker](ACCOUNTING_CHECKPOINTS.md) and [final report](ACCOUNTING_FINAL_REPORT.md) for pending checkpoints 05–14.
