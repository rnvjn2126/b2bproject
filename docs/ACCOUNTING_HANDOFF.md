# Accounting handoff

## Checkpoint 00 · Repository preparation

- **Branch and starting commit:** `ai/accounting-overnight`, based on `ai/steel-accounting` at `c9659aa490d51902cb214925cfdf973d4f5f0bb8`. The older available branches `ai/steel-mvp-overnight` and `development` precede the native accounting work. The starting checkout was clean.
- **Completed:** inspected branch history, Django app wiring, company ownership, posting boundaries, billing and relevant existing tests. Established a modular architecture and dependency order.
- **Pending:** Checkpoints 01–14 are assigned. Checkpoint 00 has no outstanding implementation.
- **Changed files:** `AGENTS.md`, `docs/ACCOUNTING_CHECKPOINTS.md`, `docs/ACCOUNTING_HANDOFF.md` and the 15 specifications under `docs/checkpoints/`.
- **Database migrations:** none added or applied to user data. Existing accounting migrations on the baseline are `0001_initial` and `0002_alter_journal_kind`.
- **Test results:** Django check passed and no migration drift was detected. Run 1 passed all 121 tests in 105.979 seconds. Run 2 passed all 121 tests in reverse order in 106.039 seconds.
- **Known errors:** no baseline suite or configuration failures observed.
- **Security:** accounting uses owner-only endpoints and workspace-scoped models; team manager and sales roles do not grant financial access. Existing CSRF, no-store and response headers apply. No privileged database tamper protections or PostgreSQL concurrency proof have been established. Use a synthetic database.
- **Accounting assumptions:** INR, Decimal to paise, India time, April–March financial years, and manual opening, general and adjustment journals. Operational quotations, subscription billing and statutory invoice posting are separate. Retain the source and effective date of any future statutory rule.
- **Latest verified baseline commit:** `c9659aa490d51902cb214925cfdf973d4f5f0bb8`.
- **Checkpoint 00 preparation commit:** `8350409933e1b23f04a225b177a121dd70b7a75b`.
- **Next instructions:** inspect Checkpoint 01 against the existing engine before adding anything. Focus on unique transaction references, duplicate submission, durable audit history and protection against silent changes. Preserve existing journal entries. Run targeted verification, then complete regression and migration checks, and record a local commit before starting Checkpoint 02.

### Existing architecture and module dependencies

| Module | Responsibility and integration boundary |
| --- | --- |
| Django project | `steel_quotes` configures templates, authentication and middleware. `dashboard` owns company workspace, memberships, catalogue, parties, enquiries, offers, quotations and billing. |
| Workspace permissions | `dashboard.accounts` resolves company membership. Operational data typically scopes to the workspace owner. `accounting` uses explicit workspace foreign keys and owner checks at its views and posting service. Preserve both scoping conventions when joining records. |
| Subscription billing | `dashboard.billing` handles Free and Business entitlements, seat and quotation quotas and simulated billing. Its plan middleware applies to dashboard routes. Keep subscription events separate from the tenant's trading books and avoid treating a paid plan as financial role permission. |
| Accounting core | Extend the existing `accounting` app. Keep chart, periods, journals and posting rules at the core. Post via atomic services with source identifiers, Decimal amounts and company validation. Reports should read posted lines; period locks and reversals stay in the core. |
| Sales and procurement | Reuse catalogue, parties, enquiries, supplier offers and accepted quotations. Snapshot commercial terms at document conversion. A quote or order creates a commitment, while a verified later event can call the posting service. |
| Inventory and costing | Stock belongs to company, warehouse and lot. Receipt and dispatch record quantities independently of invoice flows. Valuation consumes stock movements and sends linked cost postings to accounting, using one transaction for a movement and required posting. |
| Settlement and banking | Allocate verified ledger receipts or payments against posted invoices. Statement imports and matches reconcile existing entries. Imported records and user-entered references do not independently verify payment. |
| Statutory and interoperability | Keep GST, filing preparation and Tally conversion behind dedicated services. Validate sources, rule dates, data formats, rights and reconciliations before enabling output. Validate proposed imports before using the same posting service. |

Keep the dependency direction toward the posting service: sales, procurement, inventory valuation and settlements can submit approved events; the accounting core does not call back into trading or stock workflows. Keep unverified financial work separate from any production workflow.
