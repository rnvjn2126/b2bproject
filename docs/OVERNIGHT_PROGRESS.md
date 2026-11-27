# Overnight accounting progress

- **Branch:** `ai/accounting-overnight`
- **Baseline:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`
- **Latest implementation commit:** `17c690dfa87b67433e36954716bafb7a62873a02`.
- **Active checkpoint:** 07, Steel-specific inventory. Partial.
- **Last verified task:** Company-scoped stock reservations, release and reservation-backed issues.
- **Changed files and migrations:** Inventory models, stock services, tests and migration 0004.
- **Latest tests:** 13 focused passed. Both full runs passed 215 tests. Django, migration drift and the disposable SQLite concurrency probe passed.
- **Exact next task:** Wire the draft inventory count and reporting modules to models and migrations and verify them before adding gated owner screens. The draft count, report and form files remain untracked. PostgreSQL and browser checks are pending.

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
