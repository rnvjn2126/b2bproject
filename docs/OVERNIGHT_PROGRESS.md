# Overnight accounting progress

- **Branch:** `ai/accounting-overnight`
- **Baseline:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`
- **Latest implementation commit:** `a0c2b5215b4415eca06996df79245f0ba4412b1a`.
- **Active checkpoint:** 09, Financial reporting. Ready to begin after verified Checkpoint 08.
- **Last verified task:** Cutting and scrap disposal, sealed sales and acquisitions, matched returns, late-cost allocation and owner ledger review.
- **Changed files and migrations:** Accounting, invoicing and inventory services, models, owner forms, views and templates. Added accounting migrations 0009–0012 and inventory migrations 0008–0012.
- **Latest tests:** 134 targeted tests passed. Django, migration drift and JavaScript syntax checks passed. Both full suites passed 261 tests. Edge at 390 px and populated SQLite accounting/inventory upgrades passed.
- **Exact next task:** Read Checkpoint 09 and inspect existing posted financial reports. Financial pilot remains default off. Review cost variances, additional correction cases and PostgreSQL before release.

## Resume on Windows

From PowerShell use the existing virtual environment. Check usage at the start and confirm the branch and worktree before editing.

```powershell
Set-Location -LiteralPath 'C:/Users/Dueolingo/Documents/Codex/2026-11-22/you-are-responsible-for-developing-my/work/steel-quotes-publish'
git status --short --branch
git log -5 --oneline
Get-Content AGENTS.md
Get-Content docs/ACCOUNTING_HANDOFF.md -TotalCount 20
Get-Content docs/checkpoints/09-financial-reports.md
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
