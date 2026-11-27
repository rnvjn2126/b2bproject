# Overnight accounting progress

- **Branch:** `ai/accounting-overnight`
- **Baseline:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`
- **Latest implementation commit:** `badcb3ed350fa02c405c0da80d526131e6d92f51`.
- **Active checkpoint:** 06, Banking and reconciliation. Partial.
- **Last verified task:** CSV and bounded XLSX staging, duplicate preview and private owner reconciliation.
- **Changed files:** banking statement reader, forms/services/tests and upload templates. OpenPyXL and defusedxml are installed in the project's virtual environment and declared in requirements.
- **Migrations:** latest is banking 0004. No migration in 06E or 06F.
- **Latest tests:** 15 banking tests passed. Both 199-test suites, migration drift, dependency checks and the phone-width XLSX confirmation and matching passed.
- **Exact next task:** wire private account/book/transfer and reference/cheque controls. Then complete Checkpoint 06 verification and proceed to structured steel inventory.

## Resume on Windows

From PowerShell use the existing virtual environment. Check usage at the start and confirm the branch and worktree before editing.

```powershell
Set-Location -LiteralPath 'C:/Users/Dueolingo/Documents/Codex/2026-11-22/you-are-responsible-for-developing-my/work/steel-quotes-publish'
git status --short --branch
git log -5 --oneline
Get-Content AGENTS.md
Get-Content docs/ACCOUNTING_HANDOFF.md -TotalCount 20
Get-Content docs/checkpoints/06-banking.md
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py check
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py makemigrations --check --dry-run
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py test --noinput
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py test --noinput --reverse
```

See the [checkpoint tracker](ACCOUNTING_CHECKPOINTS.md) and [final report](ACCOUNTING_FINAL_REPORT.md) for pending checkpoints 05–14.
