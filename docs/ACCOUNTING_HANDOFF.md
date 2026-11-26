# Accounting handoff

## Checkpoint 04A · GST calculation foundation

- **Completed:** introduced company GST registration records, dated HSN/SAC rate lookup and a Decimal calculator for domestic CGST/SGST/UTGST/IGST, percentage cess, discounts, freight, inclusive pricing and round-off. Added Indian amount in words and recorded official sources.
- **Pending:** sales and purchase drafts, approved registrations, issue numbering, statutory snapshots, posted GST ledgers, notes, returns and A4 output. The calculator is internal and has no public or posting routes.
- **Changed files:** new `invoicing/` app, `steel_quotes/settings.py`, GST source register, checkpoint tracker and handoff.
- **Migrations:** invoicing `0001_initial`. Adds registration and rate tables without seeding rates or altering trading records.
- **Tests:** four targeted tests passed. Full run 1 passed 135 in 132.120 seconds. Reverse run 2 passed 135 in 132.417 seconds. Django and migration checks passed.
- **Security and accounting assumptions:** GSTIN validation checks the regular format. Explicit domestic place of supply and local tax component are required. Rates and actual tax treatment require review. No official approvals, payment or return submission are generated.
- **Latest verified implementation commit:** `9af837825f8b0a6693b346ff32c29c4c32462845`.
- **Next instructions:** checkpoint 04B should add company-owner-only internal draft snapshots linked to eligible confirmed dispatches or receipts. Start with one movement per draft and prove company isolation, duplicate prevention and quote/PO rate preservation.

## Checkpoint 03 · Sales and purchase orders

- **Completed:** accepted quotations convert once per quotation series. Sales terms and customer details are snapshotted. Sales and purchase orders have references, delivery dates, approval/cancellation attribution, printable PDFs and pending reports. Separate supplier allocations support split procurement. Goods receipts and dispatch record partial quantities and reject duplicates and quantities beyond the requirement or available receipts.
- **Pending:** Checkpoint 04 invoicing and GST. Inventory, valuation and ledger effects are separate downstream work. PostgreSQL concurrency execution remains a release gate.
- **Changed files:** new `orders/` app and `templates/orders/`, project settings and URLs, workspace navigation and quote detail, accounting architecture, tracker, handoff and test results.
- **Migrations:** orders `0001_initial` and `0002_purchaseorder_ordermovement_and_more`. No existing quotation data is modified.
- **Tests:** 6 focused order tests passed. The first targeted run found an assertion text mismatch, corrected before verification. Full run 1 passed 131 tests in 84.364 seconds. Reverse run 2 passed 131 in 84.370 seconds. Django and migration checks passed. Chrome verified native quote acceptance, conversion, approval and mobile order detail.
- **Known errors and security concerns:** no final test failures. Owners and managers can view orders. Mutations require a valid owner or manager seat. Supplier PDFs exclude buyer details and customer order PDFs exclude procurement and margin data. PostgreSQL and full integration remain unverified.
- **Accounting assumptions:** one sales order per quote series. One purchase order per sales requirement and selected offer, with multiple orders for split suppliers. PO rates represent normalized material before tax and freight. Dispatch requires recorded receipts through the dispatch date. Orders and movements do not create journals or warehouse stock.
- **Latest verified implementation commit:** `c66732c217dc916b8eb82f5935d9669bb428593c`.
- **Next instructions:** read Checkpoint 04 and the GST source register. Start with statutory source review and a synthetic, versioned tax calculation slice. Invoice issuance and posting must be separate from accepted orders and tied to explicit eligible quantities. Keep statutory functionality disabled or separate until professional review and verification.

## Checkpoint 02 · Ledgers and voucher management

- **Completed:** expanded the Indian starter chart. Added eight internal voucher types with draft entry, numbered review, revision checks and owner approval through the shared posting service. Added the date and branch filtered day book. Reused general ledger and trial balance.
- **Pending:** Checkpoint 03 order conversion and procurement. GST and statutory notes are separate. PostgreSQL verification remains open.
- **Changed files:** `accounting/forms.py`, `models.py`, `services.py`, `tests.py`, `urls.py`, `voucher_views.py`, migration 0005, accounting navigation and voucher/journal/day book templates, and accounting tracker, handoff, test, architecture and security documents.
- **Migration:** `0005_alter_journal_kind_voucherdraft`. Re-run financial-year setup to add new starter groups to an existing workspace. Existing ledger classifications remain intact.
- **Tests:** 16 targeted accounting tests passed. Run 1 passed 125 tests in 132.136 seconds. Reverse run 2 passed 125 tests in 131.931 seconds. Django and migration checks passed. Chrome verified draft creation, approval and the mobile day book.
- **Known errors and security concerns:** no test failures. Draft and approval endpoints are company scoped and owner-only. Privileged database controls and PostgreSQL test gates remain as above.
- **Accounting assumptions:** internal sales and purchase vouchers are manually approved accounting entries. Debit notes reduce supplier liabilities. Credit notes reduce customer receivables. No statutory tax calculation or automatic invoice allocation was added.
- **Latest verified implementation commit:** `bc4ac68f0fa93f618cd1580a1525d86d5a957eb6`.
- **Next instructions:** read Checkpoint 03. Introduce a separate operational order layer. Convert accepted quotes transactionally with private selling snapshots and a unique source link. Ship multiple supplier allocations, fulfilment, cancellation, reporting and PDF in small verified slices. Quotation and order acceptance must not post journals.

## Checkpoint 01 · Double-entry accounting engine

- **Completed:** reused the company chart, years and periods, journal forms, exact debit/credit validation, posting idempotency, locks and reversals. Added stable `JRN-<id>` references, owner-only posting and period audit history, sealed journal records and database guards.
- **Pending:** Checkpoint 02 voucher workflow. Verify PostgreSQL execution and concurrency on an isolated server before production.
- **Changed files:** `accounting/models.py`, `services.py`, `statements.py`, `tests.py`, `urls.py`, `views.py`, migrations 0003–0004, the accounting navigation, journal and audit templates, and accounting tracker, handoff, test, architecture and security documents.
- **Migrations:** `0003_journal_sealed`, `0004_accounting_guards`. Existing journals are checked for balance, then sealed. Verified on a populated synthetic SQLite database.
- **Tests:** 14 focused accounting tests passed. Run 1 passed all 123 in 127.419 seconds. Reverse-order run 2 passed all 123 in 126.062 seconds. Django, migration drift and Chrome journal/audit checks passed.
- **Known errors and security concerns:** no SQLite failures after verification. PostgreSQL triggers were not executed here. Privileged database administrators remain outside the guard boundary. Guarded SQLite tables must retain their triggers during schema changes.
- **Accounting assumptions:** internal transaction references are unique; external reference text can repeat. Unsealed rows stay out of posted reports. Closed periods and posted records use reversals and subsequent open periods for corrections.
- **Latest verified implementation commit:** `d6dc590e12c5cad18ec5d5d13655732280836dd2`.
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
