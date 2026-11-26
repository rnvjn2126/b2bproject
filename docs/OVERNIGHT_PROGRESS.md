# Overnight accounting progress

- **Branch:** `ai/accounting-overnight`
- **Baseline:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`
- **Latest verified implementation commit:** `c504e0b1addf90e0abc7531ef59973b683b71297`
- **Active checkpoint:** 04, Invoicing and Indian GST. Checkpoint 04 remains partial.
- **Last verified task:** owner-only, company-scoped internal sales and purchase draft preparation for one confirmed dispatch or receipt. A snapshot preserves the pricing, quantities, GST inputs, rate version and calculated amounts at preparation. The internal service creates no journal.
- **Changed files:** `invoicing/models.py`, `invoicing/services.py`, `invoicing/tests.py`, `invoicing/migrations/0002_invoicedraft.py`, and the GST and checkpoint records. The previous slice added the `invoicing` app and migration 0001.
- **Migrations:** 0001 and 0002 are exercised by the synthetic test suite. Apply them to a dedicated development database when running a local preview.
- **Latest tests:** 7 focused tests passed. Full run 1 passed 138 tests in 133.842 seconds. Reverse run 2 passed 138 tests in 134.857 seconds. Django and migration checks passed.
- **Known issues and release gates:** the initial focused 04B run had a synthetic fixture error, fixed before verification. No open test failure is known. Drafts are indicative and use one movement, movement date, and stored sales/PO price. Party GSTIN is format-only. The statutory review, invoice posting, full-month simulations and PostgreSQL execution are open.
- **Exact next task:** 04C, add an owner-only internal draft workflow using `prepare_draft`. Begin with registration and dated rate setup with source recording, then show a draft preview for an eligible movement. Use server-side company scoping, CSRF-protected POST and a durable internal-draft label. Keep issuance and financial posting disabled until their own tested slice.
- **After 04C:** implement approved, immutable issue snapshots and transactionally post balanced sales/purchase and GST ledger entries using the existing posting service. Implement reversal and returns, statutory notes and A4 print. Consult official sources and gate production use pending professional verification. Run regression twice before closing 04. Then resume Checkpoint 05.

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
