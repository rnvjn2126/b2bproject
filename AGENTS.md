# Agent instructions: Steel Quotation MVP

Read `docs/PRODUCT_BRIEF.md` before coding. Develop a working Django steel-trader quotation application with tests, incrementally and in the order defined by the current task.

- Develop locally on the `development` branch. The user authorized code updates to that branch only; never merge to `main` or deploy.
- User delegates ordinary reversible implementation decisions. Default to simple Django templates, India/INR, metric quantities and synthetic data; record non-obvious decisions in `docs/ASSUMPTIONS_AND_QUESTIONS.md`.
- Put genuine business uncertainties in that same document and your structured final answer. Continue with safe independent work without blocking for routine clarifications.
- Never store or access production credentials, real customer contact lists, payment information, or confidential supplier rates.
- Never send WhatsApp messages, emails or notifications to real contacts. Click-to-chat links should be explicitly staff-triggered.
- Use Python Decimal for monetary calculations, validate every quantity and unit, and distinguish margin from markup.
- Protect account ownership boundaries on all objects, exports, and PDFs.
- Keep migration files consistent. Include automated tests for every new feature and permission boundary.
- Do not disable automated tests or modify CI, repository security settings, or production infrastructure.
- The external overnight controller runs `manage.py check`, `makemigrations --check --dry-run`, and `manage.py test --noinput` and records tested Git checkpoints.
- If unclear, take the least risky reversible approach and state it. Never fabricate test results.

## Accounting checkpoint instructions

These user-approved rules supersede the earlier branch rule for accounting work. Use the local `ai/accounting-overnight` branch, based on the most complete appropriate branch, and preserve existing user changes. Require explicit permission for any remote push, deployment or spending. Keep this branch separate from main and development.

- Inspect relevant existing functionality before changing it. Reuse existing Django models, services, components and dependencies where practical. Keep changes small and avoid rebuilding delivered features or repeatedly scanning the repository.
- Work on the currently assigned checkpoint. Proceed to another only when its prompt or the autonomous runner authorizes it, after completing the required checkpoint checks. Document blockers and continue independent in-scope work.
- Work with synthetic test data. Enforce company isolation and server permissions. Use Decimal for money and preserve existing security protections. Keep incomplete or unverified financial features disabled or separate from production workflows.
- Follow the existing UI and accessibility conventions. Use official sources for statutory requirements, record unresolved legal, taxation and accounting decisions, and use original code and design without copying Tally branding or interface.
- Run targeted tests during implementation and the full regression suite before completing a checkpoint. Run Django configuration and migration drift checks. Report only executed results, keep progress concise, and make small recoverable local commits.
- Update [checkpoint status](docs/ACCOUNTING_CHECKPOINTS.md) and the [handoff](docs/ACCOUNTING_HANDOFF.md) before stopping or moving forward. Record the checkpoint number, completed and pending tasks, changed files, migrations, test results, known errors, security concerns, accounting assumptions, verified commit hash and next instructions. Record a checkpoint complete only after its implementation, verification, regression checks and documentation pass.
- The owner has assigned Checkpoints 00–14 for this run. Begin each automatically after the prior checkpoint. Split large checkpoints into verified slices and continue with independent tasks if dependencies permit. Use only the active file in `docs/checkpoints/` and its relevant dependencies. At a resource limit, leave a recoverable commit, precise next task and actual verification results. Record completed, partial, blocked and pending work in the final report.
