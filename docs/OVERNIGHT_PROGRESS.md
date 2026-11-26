# Overnight accounting progress

- **Branch:** `ai/accounting-overnight`
- **Baseline:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`
- **Latest implementation commit:** `b66a8d6124ff0398f4df93c10b68e40a66cfcb4b`.
- **Active checkpoint:** 04, Invoicing and Indian GST. Partial.
- **Last verified task:** internal sales and purchase issuance. Purchase postings require reviewed actuals and preserve the supplier reference and tax treatment with one sealed journal.
- **Changed files:** accounting and invoicing models and services, purchase draft form, views and templates, tests and documentation.
- **Migrations:** accounting 0007 and invoicing 0005. Applied and upgraded on disposable SQLite with existing sales records.
- **Latest tests:** 40 focused tests passed. Both 155-test suites passed (87.681 and 86.535 seconds). Django and migration checks passed. Chrome verified purchase actuals on mobile. A populated upgrade preserved existing sales and protections.
- **Pending:** cancellation, notes, returns and A4 printing. Production release requires legal review and PostgreSQL execution. No public issue interface is available.
- **Exact next task:** reverse issued invoices in an open period through an owner-only correction service and immutable linked correction record. Keep the generic reversal path unavailable for invoice journals. Then add partial notes and returns, and print.

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
