# Overnight accounting progress

- **Branch:** `ai/accounting-overnight`
- **Baseline:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`
- **Latest implementation commit:** `d421aa46f1545bbdc220c7b7cae949a62c2ac36a`.
- **Active checkpoint:** 07, Steel-specific inventory. Complete for the local pilot. Work paused by request.
- **Last verified task:** Owner inventory workflow, including counts, reorder alerts, lot ageing and readable phone tables.
- **Changed files and migrations:** Inventory models, services, forms, tests and templates, accounting routes and home link, and inventory migrations 0001–0005.
- **Latest tests:** 21 inventory tests passed. Both final full runs passed 223 tests after the phone layout fix. Django, migration drift, Chrome, populated SQLite upgrade and two-thread stock probes passed.
- **Exact next task:** When asked to resume, read the Checkpoint 08 specification and inspect the stock movement and sealed posting interfaces before designing company-scoped stock cost layers. PostgreSQL and certificate review remain release gates.

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
