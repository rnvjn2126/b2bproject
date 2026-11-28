# Overnight accounting progress

- **Branch:** `ai/accounting-overnight`
- **Baseline:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`
- **Latest implementation commit:** `29b90a0475702b1cd2f15c9e9f33edc491d5970c`.
- **Active checkpoint:** 11, customer acquisition. Checkpoint 10 is verified for the gated local file pilot.
- **Last verified task:** Owner preview and confirmation for the Tally XML and XLSX file migration pilot.
- **Changed files and migrations:** Accounting Tally import/export and owner workflow, shared workbook safety inspector, tests and migration 0013.
- **Latest tests:** 51 targeted and 278 in each full run passed. Django and migration drift checks passed. Edge exercised the Tally XML upload, preview, confirmation, history and voucher export at 390 px.
- **Exact next task:** Start deterministic extraction with manual review in the existing new-enquiry workflow. Tally JSON, advanced imports and live TallyPrime tests remain open. Financial pilot remains default off. Review cost variances, additional correction cases and PostgreSQL before release.

## Resume on Windows

From PowerShell use the existing virtual environment. Check usage at the start and confirm the branch and worktree before editing.

```powershell
Set-Location -LiteralPath 'C:/Users/Dueolingo/Documents/Codex/2026-11-22/you-are-responsible-for-developing-my/work/steel-quotes-publish'
git status --short --branch
git log -5 --oneline
Get-Content AGENTS.md
Get-Content docs/ACCOUNTING_HANDOFF.md -TotalCount 20
Get-Content docs/checkpoints/11-customer-acquisition.md
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
