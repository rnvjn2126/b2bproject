# Overnight accounting progress

- **Branch:** `ai/accounting-overnight`
- **Baseline:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`
- **Latest verified implementation commit:** `69711d4225fee84994db1df728ad08baf505ea67`
- **Active checkpoint:** 04, Invoicing and Indian GST. Checkpoint 04 remains partial.
- **Last verified task:** owner-only GST settings for company registrations and append-only dated rates. The earlier owner-only draft service creates one sales or purchase draft from a confirmed dispatch or receipt and has no ledger effect.
- **Changed files:** `accounting/urls.py`, `invoicing/forms.py`, `invoicing/views.py`, `invoicing/tests.py`, `templates/accounting/base.html`, `templates/invoicing/settings.html` and the GST and recovery documentation.
- **Migrations:** no new migration in 04C. Invoicing migrations 0001 and 0002 were exercised on disposable SQLite. Apply them to a dedicated development database when previewing from an older checkout.
- **Latest tests:** nine focused tests passed. Full run 1 passed 140 tests in 132.872 seconds. Reverse run 2 passed 140 tests in 133.848 seconds. Django and migration checks passed. Native Chrome verified registration submission and the settings layout at a 390 px viewport.
- **Known issues and release gates:** the earlier 04B synthetic fixture error was corrected. GSTIN validation covers the regular format. Statutory review, invoice posting, full-month reconciliation and PostgreSQL execution remain open.
- **Exact next task:** add owner-only draft creation and preview. Use a company-scoped eligible movement selector, validate the registration and HSN, call `prepare_draft` on POST and render the saved draft clearly labelled 'Internal draft'. Test cross-company access, replay, CSRF and absence of ledger writes.
- **After the preview:** implement approved, immutable issue snapshots and balanced sales/purchase and GST ledger entries through the shared posting service. Add reversals, returns, notes and A4 print. Consult official sources and require professional review before production. Run full regression twice before closing 04 and resuming 05.

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
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py test invoicing orders accounting --noinput
```

See the [checkpoint tracker](ACCOUNTING_CHECKPOINTS.md) and [final report](ACCOUNTING_FINAL_REPORT.md) for pending checkpoints 05–14.
