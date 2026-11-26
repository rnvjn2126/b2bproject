# Overnight accounting progress

- **Branch:** `ai/accounting-overnight`
- **Baseline:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`
- **Latest implementation commit:** `7fae3d26d82954a799fc77e95630b0cb2125c4f1`. Both invoice draft screens and posting proposals have focused verification.
- **Active checkpoint:** 04, Invoicing and Indian GST. Checkpoint 04 remains partial.
- **Last verified task:** calculate balanced, write-free invoice posting proposals and validate the selected ledger mappings. The owner draft screens are browser-tested.
- **Changed files:** `invoicing/posting.py`, `invoicing/tests.py` and accounting, GST and recovery documentation.
- **Migrations:** none for 04D–04F. Invoicing migrations 0001 and 0002 have been exercised on disposable SQLite.
- **Latest tests:** 04D passed 142 tests twice and Chrome draft checks. 04E passed 145 tests twice. 04F passed 31 focused invoicing and accounting tests. Django and migration checks passed. 04F full results are pending.
- **Known issues and release gates:** statutory issue, posting, regulated workflows, professional review, complete financial month reconciliation and PostgreSQL execution remain open. No issue or posting endpoint is present.
- **Exact next task:** confirm the 04F regression results, then create an internal issue service that can atomically preserve an immutable invoice snapshot, allocate workspace/financial-year numbering and link to one sealed journal. Use synthetic data, enforce owner authorization and period locks, and gate production issue pending professional review. Notes, returns, A4 print and Checkpoints 05–14 remain pending.

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
