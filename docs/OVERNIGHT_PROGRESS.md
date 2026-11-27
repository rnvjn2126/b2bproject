# Overnight accounting progress

- **Branch:** `ai/accounting-overnight`
- **Baseline:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`
- **Latest implementation commit:** `1a8f03e1226a100ba311557f2d6ab29399e1dd1d`.
- **Active checkpoint:** 05, Receivables, payables and payments. Partial.
- **Last verified task:** append-only customer/supplier bill allocation and reversal-aware as-of outstanding and unassigned balances.
- **Changed files:** settlement models, allocation service, projections, tests and checkpoint documentation.
- **Migrations:** settlements 0003, verified on disposable SQLite.
- **Latest tests:** 60 focused. Both full suites passed 175 (83.100 and 83.078 seconds). Checks passed. File-backed SQLite competing allocations were correctly capped.
- **Pending:** terms, credit limits, MSE tracking, private statements and action pages, and reminder drafts.
- **Exact next task:** add contractual credit defaults and reviewed MSE deadline inputs, then connect owner-only statements and settlement operations. Use official sources and keep statutory classification opt-in.

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
