# Overnight accounting progress

- **Branch:** `ai/accounting-overnight`
- **Baseline:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`
- **Latest implementation commit:** `1c8d2ebc529c7f8e2c08707b8092afba25c8f9ce`.
- **Active checkpoint:** 10, Tally migration and interoperability. Ready to begin after verified Checkpoint 09.
- **Last verified task:** Owner finance dashboard, sealed registers and authorised PDF, Excel and CSV exports.
- **Changed files and migrations:** Accounting report services, routes, owner forms and templates, invoicing snapshots, shared export sanitisation and tests. No migration in Checkpoint 09.
- **Latest tests:** 118 targeted tests passed. Django and migration drift checks passed. Edge, PDF rendering and workbook checks passed. Both full regression runs passed 270 tests. Three export tests passed again after layout polish.
- **Exact next task:** Read Checkpoint 10 and verify current official TallyPrime import and export formats before implementing preview or field mapping. Financial pilot remains default off. Review cost variances, additional correction cases and PostgreSQL before release.

## Resume on Windows

From PowerShell use the existing virtual environment. Check usage at the start and confirm the branch and worktree before editing.

```powershell
Set-Location -LiteralPath 'C:/Users/Dueolingo/Documents/Codex/2026-11-22/you-are-responsible-for-developing-my/work/steel-quotes-publish'
git status --short --branch
git log -5 --oneline
Get-Content AGENTS.md
Get-Content docs/ACCOUNTING_HANDOFF.md -TotalCount 20
Get-Content docs/checkpoints/10-tally-integration.md
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
