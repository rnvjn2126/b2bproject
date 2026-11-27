# Overnight accounting progress

- **Branch:** `ai/accounting-overnight`
- **Baseline:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`
- **Latest implementation commit:** `5c93e4c9b3c32c0400d63e3e1c7ef1fd2f9543e9`.
- **Active checkpoint:** 07, Steel-specific inventory. Partial.
- **Last verified task:** company warehouse and lot setup, stock receipts/issues/transfers, isolated balances and exact order-document linkage.
- **Changed files and migrations:** inventory models/setup/movement services and tests, migrations 0002–0003.
- **Latest tests:** 11 focused passed. Django and migration checks passed. Both 206-test full runs apply to 07A.
- **Exact next task:** reservations, dated release/fulfilment, then physical count/reorder/ageing and gated owner screens. PostgreSQL trigger execution remains pending.

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
