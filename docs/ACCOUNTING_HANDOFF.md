# Accounting handoff

## Checkpoint 01 · Double-entry accounting engine

- **Completed:** reused the company chart, years and periods, journal forms, exact debit/credit validation, posting idempotency, locks and reversals. Added stable `JRN-<id>` references, owner-only posting and period audit history, sealed journal records and database guards.
- **Pending:** Checkpoint 02 voucher workflow. Verify PostgreSQL execution and concurrency on an isolated server before production.
- **Changed files:** `accounting/models.py`, `services.py`, `statements.py`, `tests.py`, `urls.py`, `views.py`, migrations 0003–0004, the accounting navigation, journal and audit templates, and accounting tracker, handoff, test, architecture and security documents.
- **Migrations:** `0003_journal_sealed`, `0004_accounting_guards`. Existing journals are checked for balance, then sealed. Verified on a populated synthetic SQLite database.
- **Tests:** 14 focused accounting tests passed. Run 1 passed all 123 in 127.419 seconds. Reverse-order run 2 passed all 123 in 126.062 seconds. Django, migration drift and Chrome journal/audit checks passed.
- **Known errors and security concerns:** no SQLite failures after verification. PostgreSQL triggers were not executed here. Privileged database administrators remain outside the guard boundary. Guarded SQLite tables must retain their triggers during schema changes.
- **Accounting assumptions:** internal transaction references are unique; external reference text can repeat. Unsealed rows stay out of posted reports. Closed periods and posted records use reversals and subsequent open periods for corrections.
- **Next instructions:** read Checkpoint 02. Preserve direct journal and cash voucher entry. Add draft voucher review and explicit approval through the shared posting service, complete the Indian chart and voucher types, and verify day book and ledger behaviour.

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
