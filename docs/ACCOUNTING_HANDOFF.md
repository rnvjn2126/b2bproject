# Accounting handoff

Current branch: `ai/accounting-overnight`.

## Checkpoint 04I · Gated invoice cancellation

- **Completed:** owner-only cancellation posts an exact reversing journal and immutable correction record in one transaction. The original invoice, supplier evidence and number are retained. The reversal can use a later open period. A matching retry returns the correction.
- **Pending:** partial sales and purchase returns with linked accounting notes, review UI/print and statutory release. Gated service only.
- **Changed files:** accounting posting service, invoicing issue/models/tests, migration `0006_invoicecancellation` and checkpoint documentation.
- **Verification:** 42 targeted tests passed. Both full suites passed 157 (82.196 s normal, 82.173 s reverse). Django and migration checks passed. Tests cover identities, journal lines, closed periods, direct mutation, foreign access, duplicate inputs and atomic rollback.
- **Release gates:** this correction is financial only. It does not void a government document or claim GST filing treatment. PostgreSQL execution remains open.
- **Verified commit:** `0cd76cccec7589d5bbd2b8a47adcbb102a298995`.
- **Exact next task:** record internal partial and full sales returns with credit adjustments and purchase returns with debit adjustments. Link to an issued invoice, guard quantities and rounding against cumulative over-crediting, and prevent full cancellation after returns.

## Checkpoint 04H · Gated internal purchase recording

- **Completed:** purchase drafts accept actual supplier unit price and invoice date. Purchase recording requires those actuals, matched totals and explicit input-tax treatment. Each record preserves a supplier document separately from its internal number. Duplicate supplier references across different receipts are rejected within the company, GSTIN and supplier financial year.
- **Pending:** cancellation and adjustment/reversal workflows, brand and A4 print, statutory review and production release. The same default-off feature gate protects both issue services.
- **Changed files:** accounting journal model and service, invoicing forms, models, draft/issue services, views, tests, templates and documents. **Migrations:** accounting 0007 and invoicing 0005.
- **Tests:** 40 focused tests passed. Full normal/reverse runs passed 155 tests in 87.681 and 86.535 seconds. Django and migration checks passed. Populated SQLite upgrade retained a sale and guards. A downgrade was prevented once purchase evidence existed. Chrome verified entering actual supplier price/date and the result at phone width.
- **Assumptions:** one supplier document per confirmed receipt in this slice. References compare case-insensitively. The supplier date is used for the draft rate lookup. Purchase accounting date must be on or after receipt and supplier dates. Eligibility for input credit remains subject to professional review. PostgreSQL execution remains pending.
- **Verified commit:** `b66a8d6124ff0398f4df93c10b68e40a66cfcb4b`.
- **Exact next task:** build an owner-only internal invoice cancellation using a separately sealed reversing journal and immutable correction record. Ensure closed original periods are handled through a valid later posting date, no identifiers are recycled, and the generic journal reversal stays blocked.

## Checkpoint 04G · Gated internal sales issue

- **Completed:** same-company owner sales issuance from a confirmed dispatch. An atomic service assigns one internal financial-year number, copies the reviewed draft and links one balanced, sealed journal. The database rejects issued-row writes/deletes and incompatible journal links. Unchanged retries return the original. Generic journal reversal rejects invoice journals until invoice corrections are implemented.
- **Pending:** purchase documents and actuals, invoice corrections, print and statutory review. The feature flag is false by default and no issue endpoint is exposed.
- **Changed files:** accounting journal kind and posting service, invoicing models, issuance service, tests and GST/tracker/handoff documents. **Migrations:** accounting `0006_alter_journal_kind`, invoicing `0003_issuedinvoice` and `0004_issued_invoice_guards`.
- **Tests:** 37 invoicing and accounting tests passed. Normal and reverse full runs passed 152 each in 80.726 s and 80.427 s. Django and migration checks passed. A disposable file-backed SQLite concurrency probe ran two simultaneous issue requests and got one issued record and one sealed journal. PostgreSQL guard execution remains pending.
- **Assumptions:** the internal posting date equals the confirmed dispatch date. The company financial-year series is internal. It does not determine statutory invoice timing, registrations, numbering or filing applicability.
- **Verified commit:** `e9294f86fa5814a8c0d0d59134d9cefb51d69255`.
- **Next task:** implement gated purchase recording with actual supplier invoice reference, date, price and confirmed total. Deduplicate by company, supplier GSTIN, supplier financial year and document reference. Validate purchase ledger lines and explicit input-tax treatment. Keep purchase and sales issue actions internal and update the immutable-record guard safely.

## Checkpoints 04E–04F · GST posting proposals and ledger mapping

- **Completed:** validate saved invoice amounts and propose balanced Decimal debit/credit lines for sales and purchase invoices. Verify totals, mutually exclusive GST components and signed round-off. Purchase proposals require an explicitly selected input-tax treatment. Resolve required ledger roles only to distinct, correctly classified same-company ledgers.
- **Pending:** authorised atomic invoice issue and posting, financial-year numbering, immutable issued snapshots, approved GST policies, purchase invoice references and actual amounts, notes, returns and A4 printing. The proposal service has no write path or public interface.
- **Changed files:** `invoicing/posting.py`, `invoicing/tests.py` and GST/checkpoint documentation. **Migrations:** none.
- **Tests:** 04E passed 14 focused invoicing tests and both full runs of 145 tests (80.401 and 80.720 seconds). 04F passed 31 focused invoicing and accounting tests. Django check and migration drift check passed. 04F full runs passed 146 tests in 81.715 and 81.984 seconds. The purchase mapping follow-up at `50f785ecd64e93a64853900afb90f0e9fa4575a8` passed 32 focused tests and both 147-test regressions (80.751 seconds normal, 80.623 seconds reverse).
- **Security and accounting:** reject damaged snapshots and foreign-company/misclassified ledgers. The modelled input-tax treatments are full recovery or inclusion in cost. Eligibility, partial credit, reverse charge, freight and legal purchase invoice treatment require further review. No statutory issue or journal write has been enabled.
- **Implementation commits:** 04E `d4fd30d7ee596a5aaacb58708b69cd8e0fd9e4a5`; 04F `7fae3d26d82954a799fc77e95630b0cb2125c4f1`.
- **Exact next task:** implement a guarded service for immutable issued invoice records. Use an approved date, a workspace/financial-year sequence, a unique source draft, a snapshot and an idempotent, sealed journal link. Test concurrency, rollback, date locks and audit behaviour before exposing any issue action. See [Windows resume commands](OVERNIGHT_PROGRESS.md).

## Checkpoint 04D · Owner invoice draft screens

- **Completed:** Accounting lists eligible confirmed dispatches and receipts. Owners can submit an internal draft and reopen its saved sales or purchase snapshot. A repeated submission opens the existing draft. No journal is posted.
- **Pending:** invoice issuance, statutory snapshots, GST ledger posting, notes, returns and print. Checkpoints 05–14 remain pending.
- **Changed files:** accounting routes and navigation, invoicing forms, service, views and tests, three draft templates and the checkpoint documents. **Migrations:** none.
- **Tests:** 17 focused invoicing and order tests passed after correcting an invalid-choice assertion. Django check and migration drift check passed. The normal and reverse full runs each passed 142 tests (84.230 and 84.471 seconds). Native Chrome verified sales and purchase drafts at desktop and phone widths.
- **Security and assumptions:** owner-only, same-company source/draft/registration, CSRF on submission and no-store responses. Continue using synthetic values. Invoice drafts cannot issue a tax document or post ledger entries.
- **Latest implementation commit:** `326c86d374afd18ca29b96a416c65c985a35df35`. Verified with focused, full and browser tests.
- **Exact next task:** design and test exact debit/credit allocations from validated snapshots before connecting any issuance or posting route. Follow [Windows resume commands](OVERNIGHT_PROGRESS.md).

## Checkpoint 04C · Owner GST settings

- **Completed:** owners can record company GST registrations and append dated GST rate versions in Accounting. The form records the rate source and checks GSTIN format, HSN/SAC fields, date, percentages and duplicates. It uses company-scoped queries, CSRF and no-store headers.
- **Pending:** connect the internal draft preparation service to a movement selector and private draft preview. Official issue numbering, immutable issued snapshots, balanced GST posting, A4 print, notes and returns remain open. Downstream checkpoints remain pending.
- **Changed files:** `accounting/urls.py`, `invoicing/forms.py`, `invoicing/views.py`, `invoicing/tests.py`, `templates/accounting/base.html`, `templates/invoicing/settings.html`, and checkpoint and GST documentation.
- **Migrations:** none in this slice. The previously added invoicing migrations 0001 and 0002 remain necessary on databases that predate Checkpoint 04.
- **Tests:** nine focused invoicing tests passed. Run 1 passed 140 tests in 132.872 seconds. Reverse run 2 passed 140 tests in 133.848 seconds. Django and migration checks passed. Native Chrome verified registration submission and the settings layout at a 390 px viewport.
- **Security and assumptions:** manager and other workforce roles cannot use settings. The list shows only the signed-in owner's company. Registration and rate setup are append-only through this page. The source is recorded as text, and the registration format check does not verify ownership or GST status. Verify statutory decisions with an Indian accounting professional.
- **Latest verified implementation commit:** `69711d4225fee84994db1df728ad08baf505ea67`.
- **Exact next task:** add the owner-only draft creation and preview screens. Select an eligible same-company movement and registration, call `prepare_draft` from a CSRF-protected POST, and preview the stored snapshot as an internal draft. Test cross-company IDs, duplicate submissions, CSRF and absence of ledger writes. Follow the commands in [overnight progress](OVERNIGHT_PROGRESS.md).

## Checkpoint 04B · Internal invoice drafts

- **Completed:** the owner-only preparation service links one confirmed dispatch or receipt to one draft. Sales drafts use the accepted selling price, purchase drafts use the PO price, and both preserve quantity, party and company details, the dated rate and component amounts. Duplicate drafts and foreign workspace input are rejected.
- **Pending:** owner screens for GST registration, rate setup and draft preview, plus issue numbering, ledger posting, immutable issued snapshots, logo and letterhead, A4 print, notes and returns. Checkpoints 05–14 have not started.
- **Changed files:** `invoicing/models.py`, `invoicing/services.py`, `invoicing/tests.py`, migration 0002, the tracker, handoff, test record, GST source register and recovery documents.
- **Migrations:** invoicing `0002_invoicedraft` adds a draft table. Both invoicing migrations were checked with synthetic disposable test databases.
- **Tests:** seven focused tests passed. Run 1 passed 138 tests in 133.842 seconds. Reverse run 2 passed 138 tests in 134.857 seconds. Django check and migration drift check passed.
- **Known issues and security:** initial focused setup omitted mandatory synthetic quotation fields, then passed after correcting the fixture. Drafts need an owner, a confirmed movement and same-company registration and rate. There are no UI, issue, export, filing or ledger endpoints in this slice.
- **Accounting assumptions:** one movement per draft, movement date used to choose the indicative rate, stored order price. Supplier invoice values, actual tax treatment, registered party details and production release require verification.
- **Latest verified implementation commit:** `c504e0b1addf90e0abc7531ef59973b683b71297`.
- **Next instructions:** read the Checkpoint 04 specification. Add an owner-only internal workflow for registration and rate setup and a connected draft preview via `prepare_draft`. Keep issuance and ledger writing out of that slice. Use the branch and commands in [overnight progress](OVERNIGHT_PROGRESS.md).

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
