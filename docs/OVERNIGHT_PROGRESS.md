# Overnight accounting progress

- **Branch:** `ai/accounting-overnight`
- **Baseline:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`
- **Latest implementation commit:** `84caf9f1c1285a7e803e646eae3597fe4c4ba414`.
- **Active checkpoint:** 07, Steel-specific inventory. Checkpoint 06 is complete for the gated local pilot.
- **Last verified task:** owner banking operations, bank books, CSV/XLSX staging and manual reconciliation.
- **Changed files:** banking operations/views/tests/templates and accounting/settlement navigation.
- **Migrations:** banking 0004 is the latest. The populated SQLite upgrade preserved staged entries and refused rollback of confirmed matches.
- **Latest tests:** 18 focused banking tests. Full runs passed 202 (185.475 and 184.366 seconds). Django and migration checks passed. Chrome verified native upload, match, funds transfer and reported UPI at 390 px.
- **Pending release concerns:** PostgreSQL trigger verification, production controls, and an audit-preserving match correction workflow. No live data or bank connections were used.
- **Exact next task:** inspect catalogue fields and order movements, then add structured steel specifications and theoretical/conversion tests before warehouse stock and reservation services.

## Resume on Windows

From PowerShell use the existing virtual environment. Check usage at the start and confirm the branch and worktree before editing.

```powershell
Set-Location -LiteralPath 'C:/Users/Dueolingo/Documents/Codex/2026-11-22/you-are-responsible-for-developing-my/work/steel-quotes-publish'
git status --short --branch
git log -5 --oneline
Get-Content AGENTS.md
Get-Content docs/ACCOUNTING_HANDOFF.md -TotalCount 20
Get-Content docs/checkpoints/07-inventory.md
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py check
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py makemigrations --check --dry-run
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py test --noinput
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py test --noinput --reverse
```

See the [checkpoint tracker](ACCOUNTING_CHECKPOINTS.md) and [final report](ACCOUNTING_FINAL_REPORT.md) for pending checkpoints 05–14.
