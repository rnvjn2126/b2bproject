# Overnight accounting progress

- **Branch:** `ai/accounting-overnight`
- **Baseline:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`
- **Latest implementation commit:** `e9294f86fa5814a8c0d0d59134d9cefb51d69255`.
- **Active checkpoint:** 04, Invoicing and Indian GST. Partial.
- **Last verified task:** gated internal sales issue creates one immutable snapshot and one balanced journal from a confirmed dispatch in one transaction.
- **Changed files:** accounting and invoicing models/services, issuance service, tests, settings and verification documentation.
- **Migrations:** accounting 0006 and invoicing 0003 and 0004. Applied to disposable SQLite. Accounting 0006 is a SQLite schema no-op for the guarded journal table.
- **Latest tests:** 37 focused passed. Full runs passed 152 each in 80.726 and 80.427 seconds. Django and migration checks passed. SQLite file-backed concurrent replay produced one record and journal.
- **Pending:** purchase issue service, invoice corrections and A4 printing. Prior professional statutory review and PostgreSQL execution remain open. No live issue interface is present.
- **Exact next task:** capture supplier actual price and documents, then add gated purchase recording with same-company validation, input-tax treatment, external reference deduplication and immutable journal linkage. Run normal and reverse tests before closing the slice.

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
