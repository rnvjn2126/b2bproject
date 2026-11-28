# Accounting handoff

Current branch: `ai/accounting-overnight`.

## Checkpoint 08E–08F · Sealed costs of sale and purchase acquisitions

- An issued sales invoice can post cost only from the exact valued stock issue linked to its approved dispatch. The owner selects the inventory asset and cost-of-sales expense ledgers. The service validates the sealed invoice, checks the period and prior asset balance, and prevents duplicate posting. Zero cost is recorded without an empty journal.
- An issued purchase invoice can capitalise only the acquisition debit supported by the exact receipt. A debit already posted to the reviewed inventory asset is linked without posting twice. Recoverable GST stays on its own ledger. Quotes and orders alone create no revenue or cost-of-sales postings.
- Costed invoices require proof of a same-lot stock receipt or issue to cancel or return. Financial correction, valuation and cost journal are atomic. Partial sales returns restore the original issue cost with cumulative paise rounding. Purchase returns stop for review when the stock issue value differs from the invoice correction. The original invoice, stock movement and cost evidence remain immutable.
- Local pilot settings keep monetary stock posting disabled by default. The owner-only acquisition, sales cost and matched invoice correction screens were exercised by Django tests. PostgreSQL, late costs, stock variances, cases without restock evidence and statutory use require review. [IFRS Foundation inventory standard summary](https://www.ifrs.org/issued-standards/list-of-standards/ias-2-inventories/)
- Implementation commits `3351a1b028cbfda082e68bc96ca9ed5a243b5ffb` and `a0eaaf5be985f5485ff2febb1618ca4aca6ed8d5`. Added accounting migrations 0009–0010 and inventory migrations 0008–0009. Focused runs passed 114 tests after sales costing and 120 after acquisitions and owner forms. Django and migration drift checks passed. The latest full suites are the earlier 242-test runs.
- Next task is the owner cutting workflow. Record an atomic issue and traced finished, remnant and scrap receipts, conserve measured mass and split existing inventory value across outputs. Then add reviewed late freight and packaging with standalone cost evidence.

## Checkpoint 08C–08D · Supplier rates and stock-to-ledger review

- Owners can record dated supplier rates and see history, availability and an expiry warning. Recommendations use the latest rate from each supplier, exclude expired records, convert kilograms and tonnes, enforce delivery limits and list quantities left unfilled. The comparison includes the full freight and packaging of each selected supplier once.
- Owners can choose the valuation method, value recorded movements and compare dated internal stock quantities and costs with a selected asset ledger. The report uses sealed journal lines, shows unvalued activity and remains private. Valuation records and recommendations create no journals or purchase orders.
- Implementation commit `958131e5d66436c86320978653ecb2f12fc64dd9`. Added inventory migration 0007 for supplier rates. Changed inventory forms, views, routes, services, models, tests and templates.
- Forty inventory tests, Django system checks and migration drift checks passed. The first recommendation test fixture did not exercise the intended fixed-fee tradeoff. Corrected the sample figures and reran the suite. Both full suites passed 242 tests (156.369 s normal, 153.826 s reverse). A populated SQLite upgrade from inventory 0005 to 0007 preserved eight units and valued the original receipt at INR 130.00. Both Chrome attempts timed out at sign-in. Browser layout for these screens remains unverified.
- Next task is to design the dedicated COGS posting and correction service around an active sealed sales invoice linked to the exact dispatch. Use the recognized invoice date, a reviewed inventory asset ledger and a reviewed COGS expense ledger. Keep the route disabled until cancellation and partial-return behavior are verified. Then add acquisition clearing and late cost allocations, followed by cutting, remnants and scrap.

## Checkpoint 08A–08B · Internal valuation foundation

- Implemented Decimal FIFO and moving weighted average, including partial issue costing and exact freight/packaging allocation. Each company selects a method. The method cannot change after the first valuation record without a formal transition. Stock costs are pooled by catalogue product and its recorded stock unit across the company.
- A valuation snapshot links once to an existing stock movement. Receipts require an explicit material amount and can include reviewed freight, packaging and other cost. Transfers preserve the pool. Issues consume the pool. Earlier unvalued movements must be processed first. Workspace locks serialize allocation, and database guards prevent edits to saved valuation snapshots.
- Implementation commits `35ec95d4c79e5e97cf21c615839b7d3be8755c31` and `ae79d2fd5ae54b2f76d824f652ac90957176d7e0`. Changed inventory costing, models, stock and valuation services and tests. Added inventory migration 0006.
- Five arithmetic tests passed. After adjusting a delete assertion to exercise the database guard on a row without protected dependants, all 31 inventory tests passed. Django and migration drift checks passed. The full 242-test results that cover this work are recorded above.
- Valuation has no website or ledger posting entry point. Fair-value and net realisable value adjustments, statutory treatment, purchase clearing, COGS timing, returns and PostgreSQL execution require further work. Before using a receipt value, confirm that its cost and tax treatment agree with the linked procurement records. [IFRS Foundation inventory standard summary](https://www.ifrs.org/issued-standards/list-of-standards/ias-2-inventories/)
- Exact next task is the independent owner supplier-rate board and procurement recommendation workflow. Then link cost events to reviewed financial sources, add stock-to-ledger reconciliation and implement cutting, remnants, scrap and returns.

## Checkpoint 07 complete · Local inventory pilot paused

- Owner screens cover steel specifications, warehouses and bins, heat and batch traceability, mill evidence, receipts, issues, transfers, reservations, physical counts, reorder review and lot ageing.
- Inventory migrations 0001–0005. This slice added 0005 for physical counts and reorder thresholds. Counts reconcile the physical quantity against the recorded position and append a stock adjustment when needed. Available stock excludes active reservations. These operational movements create no financial journals.
- Changed inventory services, models, migrations, forms, URLs and tests, plus inventory and accounting templates and local Django settings. Count and reporting implementation `9a2961056298b7e02e571616fde53d3d69c7736b`. Owner screens `722f7e8a853d7ed0bc2e5c732edb29da386a2bd3`. Latest verified implementation `d421aa46f1545bbdc220c7b7cae949a62c2ac36a`.
- Twenty-one inventory tests, Django and migration drift checks passed. After the template layout fix, the two full regression runs each passed 223 tests (237.366 s normal, 239.271 s reverse).
- Chrome verified the owner link, a measured-weight transfer, physical count adjustment, reorder alert and certificate upload at 390 px. The first mobile layout wrapped column headings into individual letters. Existing scrollable table styles fixed the layout, and the final browser check verified the scroll region and readable column widths.
- A disposable SQLite upgrade from populated inventory migration 0004 preserved the original movement and quantity, then recorded a count on 0005. The first probe used a current service against the old schema and failed because the stock-count table was absent. Seeding only old-schema fields fixed the probe. With two competing workers, one reservation and one issue each succeeded and their competing requests were rejected. Final on hand/reserved/available was 8/8/0.
- Production release remains gated on PostgreSQL verification and certificate review. Certificates are owner-only attachment downloads. Ageing uses the earliest ordinary receipt for the lot. It shows unknown if the stock was found only through a count. See [inventory assumptions](ASSUMPTIONS_AND_QUESTIONS.md#steel-inventory-pilot-27-november-2026).
- The user requested a pause after Checkpoint 07. Development is paused at this checkpoint. When the user resumes, read Checkpoint 08 and inspect the posted movement and ledger interfaces before designing cost layers and valuation postings. No valuation work has started.

## Checkpoint 07D · Atomic stock reservations

- Verified company-scoped reservations, release and optional reservation-backed stock issue. Stock, reservation balances and audit evidence update in one transaction. Inventory movements do not post financial journals.
- Changed inventory models, stock services and tests. Added inventory migration 0004. Implementation commit: 17c690dfa87b67433e36954716bafb7a62873a02.
- Thirteen focused tests passed. Both full runs passed 215 tests (240.590 s normal, 240.969 s reverse). Django and migration drift checks passed. A disposable SQLite two-thread probe admitted one of two competing reservations and one of two competing issues, leaving eight on hand, eight reserved and zero available.
- PostgreSQL concurrency and browser verification remain pending. Untracked drafts in inventory/counts.py, inventory/reports.py and inventory/forms.py have not been integrated or tested.
- Next task is to connect physical stock counts and reorder/ageing reports to the inventory models and migrations, verify them, then connect the gated owner screens.

## Checkpoints 07B–07C · Traceable locations and stock movements

- Company warehouses and storage locations can hold isolated catalogue lot positions. Lots snapshot unit, grade and weight and hold heat, batch, mill and manufacturer details with bounded PDF evidence.
- Receipts, issues and transfers validate the company and available quantity and atomically adjust positions and append immutable movements. A movement can link once to a compatible approved order receipt or dispatch. Measured kilograms and theoretical weights are recorded separately. No general ledger entries are posted.
- Inventory migrations 0002 and 0003. Implementation commits `a522242131516d0742a50bcea0cb418763d4854f` and `5c93e4c9b3c32c0400d63e3e1c7ef1fd2f9543e9`.
- Seven focused tests passed for 07B and eleven for 07C after reloading a synthetic OrderMovement so its persisted quantity deserializes as Decimal. Django and migration checks passed. The last full 206-test runs apply to 07A. PostgreSQL and the rest of the warehouse workflow remain open.
- Exact next task is atomic stock reservations, releases and reservation-backed issues. Then add physical counts, reorder/ageing and owner screens. Mill certificates are opaque downloads. Header and size checks identify accepted files. Supplier provenance and malware screening require separate release review.

## Checkpoint 07A · Structured steel specifications

- Added catalogue-linked grade, geometry and density records for bars, TMT, sheet, plate, pipe, coil, angle, channel and beam. Conversions support kg, tonne, metre and piece and distinguish theoretical and explicitly measured weight.
- Four focused tests passed. Both full suites passed 206 (292.799 s normal, 285.192 s reverse). Django and migration drift checks passed.
- Inventory migration 0001 and implementation commit `ec4d114ec2c83944cc18895334dde38cbb1e7652`. Existing catalogue descriptions and recorded actual weights remain intact. Angles, channels and beams use simplified section geometry. This estimate excludes rolled fillets and TMT ribs. Density is entered explicitly.
- Next task is to register company warehouses and storage locations, snapshot traceable lots and preserve independently supplied mill-test certificate evidence before posting stock moves.

## Checkpoint 06 complete · Internal banking pilot

- Company bank, cash and petty cash accounts, ledger books, transfers, manually reported UPI/NEFT/RTGS/IMPS references and cheque events are available in the gated owner workflow. CSV and XLSX support preview, explicit confirmation, duplicate handling, suggested/manual matching and unmatched totals.
- Exact reference search covers candidates outside the default seven-day window. Matches are immutable. A future correction should preserve both the old match and a separate reversal event.
- Both final full suites passed 202 (185.475 s normal, 184.366 s reverse). Eighteen banking tests, Django/migration checks, Chrome at 390 px and a populated SQLite 0003→0004 upgrade passed. The first upgrade probe targeted only banking and left auth migrations incomplete. Migrating all apps before preparing the older banking schema fixed the probe.
- Implementation commit `84caf9f1c1285a7e803e646eae3597fe4c4ba414`. No migration in 06G. Latest banking migration 0004. PostgreSQL and release review remain pending. All banking evidence and browser data were synthetic.
- Exact next task is Checkpoint 07. Inspect the existing catalogue and order movements, then implement structured steel geometry, theoretical weights and explicit unit conversions while preserving actual weights and current quotation behavior.

## Checkpoint 06F · Excel statement import

- Bounded XLSX parsing shares the CSV row validation, preview and duplicate detection. Formulas, external links, macros and unsupported archives are rejected.
- Both full suites passed 199 tests (237.205 s normal, 236.546 s reverse). Django, migration drift and dependency checks passed. Chrome verified XLSX upload, confirmation and manual matching at 390 px after a synthetic server startup retry.
- Implementation commit `badcb3ed350fa02c405c0da80d526131e6d92f51`. No migration. Added OpenPyXL and defusedxml to the requirements.
- Next task is to expose safe owner controls for bank/cash/petty cash account registration and books, internal transfers and manually reported instruments and cheque history.

## Checkpoint 06E · Private statement upload

- Owners can preview and confirm CSV imports. The confirmation binds account and file and reports already imported rows. The upload remains internal and posts no ledger entries.
- Both full regression runs passed 197 tests (204.046 s normal, 204.360 s reverse). Django and migration checks passed. Browser review is pending.
- Implementation commit `1d9b004d46d40113ffe2abfb658f586e74f17154`. No database migration.
- Next task is to plug bounded XLSX support into the same preview and staging service, then verify cross-format overlap and browser behavior.

## Checkpoint 06D · Private bank reconciliation

- **Completed:** ranked candidate matching by reference and date for equal amounts and directions, explicit owner confirmation, immutable one-to-one match records and an unmatched movement report. The gated owner screen lists suggested candidates and requires CSRF for confirmation. Neither suggestions nor confirmation create a journal or independently verify payment.
- **Changed files:** banking models, migration 0004, reconciliation service and views, tests, accounting routes and banking/settlement templates.
- **Tests:** 47 focused tests passed. Django and migration checks passed. The initial reverse regression passed 195 tests on the service slice. The initial normal run saw an in-progress template update and failed three URL reversals. Both reruns passed 196 tests on the finished workflow, in 139.831 seconds normal and 139.012 seconds reverse.
- **Gaps:** PostgreSQL guards and browser review remain unverified. The screen only offers the top 20 candidates within seven days. Match corrections and a broader manual selector are pending.
- **Implementation commit:** `979e6d435076f6914b8db62cc1c1087eb6306f00`.
- **Exact next task:** expose the owner CSV upload/preview/confirm flow, then add bounded Excel parsing and reconciliation corrections. Keep imports separate from journal posting.

## Checkpoint 06C · Bank statement CSV staging

- **Completed:** bounded UTF-8 CSV validation and read-only preview, followed by explicit digest-confirmed import. Preview binds the file to one bank account. Imports save normalized statement lines and audit batches atomically. Exact replay returns the existing batch. Overlap is account-scoped and requires explicit confirmation to skip known rows. Staging creates no journal and does not verify payment.
- **Pending:** matching suggestions, manual reconciliation, unmatched review, Excel parsing and owner banking pages. Checkpoint 06 remains partial. Checkpoints 07–14 remain pending.
- **Changed files:** banking models, CSV parser, statement service, tests, migration and required progress documents. **Migration:** banking `0003_statementbatch_statementline_and_more`.
- **Tests:** 45 focused tests passed. Both full suites passed 194 (85.976 s normal and 85.390 s reverse). Django and migration checks passed. Tests cover malformed/future rows, repeat source lines, overlap, replay, account/actor boundaries, preview digests, rollback and no ledger effects.
- **Known gaps:** CSV preview/import currently has no website endpoint. Excel support requires evaluation of a safe, bounded reader. The current interpreter has no OpenPyXL. PostgreSQL guards/concurrency and actual statutory release remain pending. No real banking data or connections were used.
- **Verified implementation commit:** `fb74ec69e71d715bef600653ced98cacb60281f2`.
- **Exact next task:** match one staged bank line to one existing sealed bank-account journal line. Suggest candidates based on amount, direction, date and reference. A scoped owner must confirm each match, preserve dated review evidence, and see unmatched statement and ledger totals. Then expose private preview and match screens and add bounded Excel support.

## Checkpoint 06B · Manual payment references and cheque events

- **Completed:** scoped UPI, NEFT, RTGS, IMPS and cheque reference recording. Optional journal-line associations require the same bank account, amount and direction. Dated cheque events record staff-reported presentation, clearing and return without ledger changes.
- **Pending:** statement CSV/Excel preview/import, matching, reconciliation, unmatched review and private bank UI.
- **Changed files:** banking models, instrument service, tests, migration and documentation. **Migration:** banking 0002.
- **Tests:** 41 focused passed. Both full runs passed 190 (83.736 s normal, 83.720 s reverse). Django and migration checks passed.
- **Verified commit:** `a0c3ede01ee35287d53d61088f3b17bca61f3a70`.
- **Exact next task:** add bounded synthetic CSV preview and committed statement staging. Reject malformed rows, detect overlaps per bank account, and keep all imports separate from the ledger. Then add Excel parsing and review-only reconciliation.

## Checkpoint 06A · Company funds accounts and books

- **Completed:** register multiple workspace bank, cash and petty-cash asset ledgers. Transfer between distinct accounts through the existing sealed contra engine. Read date-filtered cash or bank books with opening, running and closing balances. Existing cash and settlement forms recognize newly registered accounts.
- **Pending:** manually recorded instrument references and cheque tracking, import, preview, reconciliation, unmatched review and private bank UI. No bank connection, raw account number or payment verification.
- **Changed files:** banking app, settings, accounting funds selection/engine, settlement forms/services and documents. **Migration:** banking 0001.
- **Tests:** 38 focused passed. Both full runs passed 187 (87.988 s normal, 87.855 s reverse). Django and migration checks passed. Tests cover cash transfers, opening/closing reconciliation, petty-cash receipts, idempotency, masking and scope.
- **Verified commit:** `17b16721b28e2a46a1152d23a98ac3900f5a7ec3`.
- **Exact next task:** store manually reported UPI, NEFT, RTGS, IMPS and cheque references with scoped association to existing journal lines. Track dated manual cheque events without marking a payment independently verified.

## Checkpoint 05F · Verified internal settlement workflow

- **Completed for the internal pilot:** owner screens post receipts/payment, allocate or release funds, capture due dates and configurable credit terms, show sales credit exposure and track reviewed MSE dates. Statements show dated outstanding, credits and unassigned funds. Overdue reminders are prepared for manual review only.
- **Pending for release:** default-off enablement review, PostgreSQL guard/concurrency tests and professional review of MSE eligibility and statutory use. Existing quote decisions are unchanged. No bank account connection or verification is implied by a reference.
- **Changed files:** invoice review, settlement forms/views/URLs/services/tests and templates, accounting and scope documents. **Migrations:** none in this slice.
- **Tests:** 69 focused tests passed after fixing blank payment narration. Both full runs passed 184 (90.558 s normal, 90.334 s reverse). Django and migration checks passed. Chrome verified native receipt posting and mobile allocation.
- **Verified commit:** `26892e4a47b8f08462aa33f9d0dbfe629046e17b`.
- **Exact next task:** start Checkpoint 06. Use the existing chart and shared cash-book posting rules to register additional company bank/cash/petty cash ledgers. Add guarded transfers and date-based books before statement parsing and reconciliation.

## Checkpoint 05E · Private statements and reminder drafts

- **Completed:** owner-only dated customer/supplier statements, receivable/payable ageing, invoice balances and active unassigned funds. Overdue customer invoices offer a reviewable reminder with an explicitly clicked WhatsApp draft link. No external messages were sent.
- **Pending:** settlement posting/credit and assignment actions for the internal pilot. Production release remains gated.
- **Changed files:** settlement forms, URLs, views, balances, tests and templates, accounting URLs and invoice navigation. **Migrations:** none.
- **Tests:** 16 settlement tests passed. Both full runs passed 181 (94.815 s normal, 94.654 s reverse). Django and migration checks passed. A test assertion quoting error was fixed. The browser harness timed out because a variable hid its path module, then timed out at sign-in under regression load. After correction and standalone retry, Chrome verified balances and the reminder at phone width.
- **Verified commit:** `d6849344edd02d4fa07dd3dc5ef6dcfa009a1de0`.
- **Exact next task:** finish owner-only POST forms for receipt/payment, bill allocation, release, contractual due dates, credit terms and reviewed MSE dates. Connect the sales credit warning without changing existing quotation approval logic.

## Checkpoint 05D · Credit controls and reviewed MSE dates

- **Completed:** company party credit terms and limits, one-time contractual default application, credit exposure and past-due calculations. Reviewed supplier invoices can record a separate MSE deadline with acceptance, written terms and evidence.
- **Pending:** private statements, posting and allocation forms, credit-warning placement, and manual reminders. Automatic eligibility classification, statutory filings and interest/tax treatment remain out of scope.
- **Changed files:** settlement models, balance projection, credit/deadline services, tests and documents. **Migration:** settlements 0004.
- **Tests:** 63 focused passed. Full runs each passed 178 (83.850 s normal, 83.726 s reverse). Django and migration checks passed.
- **Assumptions:** conservative positive receivable exposure, party credit defaults do not rewrite prior due dates, MSE tracking starts only after documented eligibility and acceptance review. Statutory source links are in the assumptions document.
- **Verified commit:** `d2ba18f4911c53ebffd7ef276fdfb807a9b49a4e`.
- **Exact next task:** expose private owner statements with ageing, unassigned funds and overdue/credit status. Then connect existing payment, allocation, release and due-date services and generate manual reminder drafts without sending messages.

## Checkpoint 05C · Bill allocations and released credits

- **Completed:** allocate current customer/supplier funds against matching posted invoices and control ledgers within an open period. Bound receipt/payout and invoice amounts, enforce retries and chronological events, and record append-only partial allocation reversals. As-of projections show invoice outstanding or credit and unassigned funds. A later return keeps the invoice credit visible until explicitly released.
- **Pending:** owner-facing statements and operations, configurable credit terms/limits, reminders and verified-eligibility MSE deadlines. Bank verification remains out of scope.
- **Changed files:** settlement allocation service, balances, models, tests and documentation. **Migration:** settlements 0003.
- **Tests:** 60 focused passed. Both full runs passed 175 (83.100 s normal, 83.078 s reverse). Django and migration checks passed. File-backed SQLite accepted only one of two competing excess allocations.
- **Assumptions:** allocation and release have no cash-ledger write. The original payment's posted reversal date controls settlement visibility. Credits and unallocated funds are separate and never moved automatically. PostgreSQL trigger and concurrency execution remain a release gate.
- **Verified commit:** `1a8f03e1226a100ba311557f2d6ab29399e1dd1d`.
- **Exact next task:** add contractual party credit settings and reviewed MSE deadline inputs using official sources. Then connect the verified services to private statements, ageing and payment/adjustment actions and manual reminder drafts.

## Checkpoint 05B · Party receipts and payments

- **Completed:** owner-scoped customer receipts and supplier payments post sealed cash/bank journals with party/control account linkage. Records are immutable. Equal retries return the original and duplicate external references on a funds ledger are rejected. Reversal visibility follows the reversal journal date.
- **Pending:** allocations, advances, adjusted balances and posting/report forms. No settlement UI yet and no independent bank verification.
- **Changed files:** settlement models, services, projections, tests and documentation. **Migration:** settlements 0002.
- **Tests:** 56 focused passed. Both full runs passed 171 (83.060 s normal, 83.065 s reverse). Django/migration checks passed. Two concurrent requests returned one payment and one sealed journal on disposable file-backed SQLite.
- **Verified commit:** `c415398b06457ab227fa03c676c240b8572f3847`.
- **Exact next task:** add append-only payment allocations and adjustment records. Enforce matching workspace, party and control ledger, positive Decimal amounts and available balances. Project allocation activity by date and replay/reversal state. Show unapplied funds and invoice credits without silently moving them.

## Checkpoint 05A · Contractual due dates and ageing foundation

- **Completed:** settlement module records a company-owner contractual due date once per issued invoice. Its as-of projection reads sealed invoices and applies posted returns and cancellations on their effective dates. Age buckets cover current, 1–30, 31–60, 61–90 and over 90 days. Missing due dates are identified separately.
- **Pending:** actual payments, advances, bill allocation, statements, terms/limits, reminder drafts and MSME tracking. Projection currently reports adjusted invoices before payment allocation and has no public or owner-facing report.
- **Changed files:** new `settlements/` app, Django app settings, shared synthetic invoice test fixture and documentation. **Migration:** settlements 0001.
- **Tests:** 53 invoicing, accounting and settlement tests passed. Both full runs passed 168 (84.823 s normal, 84.381 s reverse). Django and migration checks passed.
- **Assumptions:** a due date records the contract, independent of the point in time it was entered. Purchase terms may start at the supplier document date before receipt/posting. Missing terms produce no overdue inference. Statutory deadlines are separate.
- **Verified commit:** `703bbb86ee449cf07b15e35324902b0134391fab`.
- **Next task:** record owner-controlled receipt/payment with a sealed journal and party/control-account mapping. Add idempotency and nonblank external reference deduplication, then extend the as-of report with allocations and reversals.

## Checkpoint 04L · Internal sales and purchase invoice workflow

- **Completed:** private owner review, issue, cancellation and return forms use the existing atomic services and default-off feature gate. An unissued purchase estimate can be replaced once with confirmed supplier actuals. Repeated issue requests must match the original inputs. Chrome verified native issue and cancellation.
- **Status:** internal invoice workflow verified. The statutory portion of Checkpoint 04 remains blocked on professional decisions about tax invoice timing/numbering, provision-specific notes, input credit and filing/e-invoice applicability. Price-only statutory notes are pending. PostgreSQL execution remains a release gate. The production issue/correction switch stays off.
- **Changed files:** accounting URLs, invoicing forms/services/views/tests and review, draft and print templates. **Migrations:** none in this slice.
- **Tests:** 50 focused tests and both 165-test full suites passed (93.157 s normal, 93.034 s reverse). Django and migration checks passed. The first Chrome run timed out at login alongside regression load, then a standalone retry passed issue, print and phone-width cancellation.
- **Verified commit:** `32511cb580d2228c0706ef46c77d209e4ebd7c81`.
- **Exact next task:** begin the independent accounting work in Checkpoint 05 using synthetically issued documents. Implement an as-of projection of posted customer/supplier invoices, cancellations/returns and ageing using contractual due dates, then company-scoped payments and allocation. Use official sources before implementing MSME deadlines.

## Checkpoint 04K · Private A4 invoice layout

- **Completed:** owners can update registration letterhead and a bounded PNG/JPEG logo. Drafts copy the branding data and issued records retain it with the document. The private A4 view displays the original amounts in words and current cancellation or return status.
- **Pending:** complete private issue/review actions for synthetic pilot operation. Statutory printing, notes not arising from returns, release and PostgreSQL verification remain open.
- **Changed files:** accounting URL registration, invoicing form, registration model, draft service, views, tests, A4 CSS/templates and documentation. **Migration:** invoicing 0008.
- **Tests:** 47 focused passed. Both full runs passed 162 (87.270 s normal, 88.029 s reverse). Django and migration checks passed. Chrome checked A4 CSS, hidden screen-only controls, logo, words and phone layout.
- **Security:** only PNG/JPEG permitted; bounded decode and re-encoding remove upload metadata. No public upload path exists. Print is owner-only, gated and noncacheable.
- **Verified commit:** `d4186fa413c75a38ff7fe43c9805549b18d4c1a6`.
- **Exact next task:** connect owner-only synthetic review controls to the existing issue and correction services. Use POST plus CSRF, preserve server-side validation and keep the operational gate off by default.

## Checkpoint 04J · Scoped internal returns

- **Completed:** partial/full sales return credits and purchase return debits link to the original invoice and distinct sealed journals. Cumulative quantity and value checks prevent over-returning. Exact component allocations reconcile to the original invoice after a full return. Returned invoices cannot be fully cancelled.
- **Pending:** A4 brand/print, owner-facing controls for verified local operations, non-return statutory notes and professional review. No stock movement or official GST output is created by returns.
- **Changed files:** accounting journal types and service, invoicing models, issuance and return services, tests and documents. **Migrations:** accounting 0008 and invoicing 0007.
- **Tests:** 45 focused passed. Both full suites passed 160 (82.130 s normal, 82.249 s reverse). Django and migration checks passed. Competing returns on a disposable file-backed SQLite database posted one note and rejected the excess.
- **Verified commit:** `d8bcefb4db111ada860a323e690662d60c226203`.
- **Exact next task:** add owner-managed company branding and an A4 printable internal invoice from the immutable snapshot. Prevent external access and keep every output clearly internal.

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
