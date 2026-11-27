# Overnight accounting progress

- **Branch:** `ai/accounting-overnight`
- **Baseline:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`
- **Latest implementation commit:** `c415398b06457ab227fa03c676c240b8572f3847`.
- **Active checkpoint:** 05, Receivables, payables and payments. Partial.
- **Last verified task:** immutable company party receipts/payment linked to correct sealed ledger journals with retry and reference protection.
- **Changed files:** settlement models, services, projections, tests and documentation.
- **Migrations:** settlements 0002, verified on SQLite.
- **Latest tests:** 56 focused. Both 171-test runs passed (83.060 and 83.065 seconds). Django and migration checks passed, plus a file-backed SQLite duplicate posting probe.
- **Pending:** bill-wise allocations, adjustments, statements, terms/credit limits, reminders and verified MSME tracking.
- **Exact next task:** add append-only allocations with seller/customer and ledger matching, caps, idempotency, adjustments and historical reversal handling.

## Resume on Windows

From PowerShell use the existing virtual environment. Check usage at the start and confirm the branch and worktree before editing.

```powershell
Set-Location -LiteralPath 'C:/Users/Dueolingo/Documents/Codex/2026-11-22/you-are-responsible-for-developing-my/work/steel-quotes-publish'
git status --short --branch
git log -5 --oneline
Get-Content AGENTS.md
Get-Content docs/ACCOUNTING_HANDOFF.md -TotalCount 20
Get-Content docs/checkpoints/05-payments.md
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py check
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py makemigrations --check --dry-run
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py test --noinput
& '..\..\b2bproject\.venv\Scripts\python.exe' manage.py test --noinput --reverse
```

See the [checkpoint tracker](ACCOUNTING_CHECKPOINTS.md) and [final report](ACCOUNTING_FINAL_REPORT.md) for pending checkpoints 05–14.
