# Overnight accounting progress

- **Branch:** `ai/accounting-overnight`
- **Baseline:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`
- **Latest implementation commit:** `958131e5d66436c86320978653ecb2f12fc64dd9`.
- **Active checkpoint:** 08, Inventory valuation and procurement. Partial.
- **Last verified task:** Owner valuation review, stock-to-ledger reconciliation and supplier rate board with split recommendations.
- **Changed files and migrations:** Inventory costing/reconciliation/procurement services, models, views, URLs, forms, tests, templates and migrations 0006–0007.
- **Latest tests:** 40 inventory tests passed. Both full runs passed 242 tests. Django, migration drift and populated SQLite 0005→0007 checks passed. Both Chrome attempts timed out at sign-in.
- **Exact next task:** Implement sealed COGS posting and corrections tied to issued sales invoices and exact dispatches. Keep financial posting gated. Acquisition clearing, landed cost adjustments, cut/remnant and scrap handling, returns and PostgreSQL verification remain open.

## Resume on Windows

From PowerShell use the existing virtual environment. Check usage at the start and confirm the branch and worktree before editing.

```powershell
Set-Location -LiteralPath 'C:/Users/Dueolingo/Documents/Codex/2026-11-22/you-are-responsible-for-developing-my/work/steel-quotes-publish'
git status --short --branch
git log -5 --oneline
Get-Content AGENTS.md
Get-Content docs/ACCOUNTING_HANDOFF.md -TotalCount 20
Get-Content docs/checkpoints/08-inventory-valuation.md
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py check
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py makemigrations --check --dry-run
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py test --noinput
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py test --noinput --reverse
```

## Preview the local inventory pilot

From this checkout in PowerShell, use a local demo database and sign in as a workspace owner.

```powershell
$env:DJANGO_DEBUG = 'true'
$env:DJANGO_INTERNAL_INVENTORY = '1'
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py migrate
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py runserver 127.0.0.1:8775 --noreload
```

Open [Steel inventory](http://127.0.0.1:8775/accounts/books/inventory/).

See the [checkpoint tracker](ACCOUNTING_CHECKPOINTS.md) and [final report](ACCOUNTING_FINAL_REPORT.md) for pending checkpoints and release gates.
