# Overnight accounting report

Work ran locally on `ai/accounting-overnight` from baseline `c9659aa490d51902cb214925cfdf973d4f5f0bb8`. The repository now contains the 15 checkpoint specifications, permanent development rules and a recovery trail.

| Checkpoint | Status | Verified outcome or remaining dependency |
| --- | --- | --- |
| 00 Repository preparation | Complete | Baseline recorded. Branch, specifications, architecture, tracker and handoff saved. |
| 01 Double-entry engine | Complete for local SQLite | Sealed journals, reference numbers, exact balance enforcement, duplicate protection, reversals, locked periods and owner audit history. PostgreSQL execution remains a release gate. |
| 02 Ledgers and vouchers | Complete for internal vouchers | Eight voucher types, draft and approval workflow, ledger statements, day book and trial balance. |
| 03 Sales and purchase orders | Complete for operational orders | Accepted quotation conversion, split procurement, approvals, cancellation, partial movements, pending reports and private PDFs. Orders do not create journals. |
| 04 Invoicing and GST | Partial | Owner GST registration and dated rate settings, domestic Decimal calculations and owner-only movement-based draft screens. Full regression on the draft screens, issue numbering, immutable issued records, ledger posting, notes, returns and print remain open. |
| 05 Receivables and payables | Pending | Requires posted invoices and settlement allocation. |
| 06 Banking | Pending | Requires posted settlement workflow and bank matching rules. |
| 07 Inventory | Pending | Goods receipts and dispatch exist operationally. The stock ledger is pending. |
| 08 Valuation and procurement | Pending | Requires verified inventory movements and accounting integration. |
| 09 Financial reports | Pending | Core statements predate this run. Complete reporting and cross-module reconciliation remain open. |
| 10 Tally migration | Pending | Requires stable import targets and verification against current TallyPrime documentation. |
| 11 Customer acquisition | Pending | Existing quote features remain. This checkpoint has no new acceptance result. |
| 12 Advanced accounting | Pending | Requires reconciled GST posting, official source review and professional verification of statutory workflows. |
| 13 Permissions and performance | Pending | Existing roles protect the delivered screens. Granular ERP roles and performance review remain open. |
| 14 Final testing | Pending | Three complete financial-month scenarios and the requested cross-module security review require the remaining verified workflows. |

## Verification

| Checkpoint | Focused tests | Full run 1 | Full run 2, reverse |
| --- | --- | --- | --- |
| 00 | Baseline | 121 passed, 105.979 s | 121 passed, 106.039 s |
| 01 | 14 passed | 123 passed, 127.419 s | 123 passed, 126.062 s |
| 02 | 16 passed | 125 passed, 132.136 s | 125 passed, 131.931 s |
| 03 | 6 passed | 131 passed, 84.364 s | 131 passed, 84.370 s |
| 04A | 4 passed | 135 passed, 132.120 s | 135 passed, 132.417 s |
| 04B | 7 passed | 138 passed, 133.842 s | 138 passed, 134.857 s |
| 04C | 9 passed | 140 passed, 132.872 s | 140 passed, 133.848 s |
| 04D | 17 passed (invoicing and orders) | Pending | Pending |

Django and migration drift checks passed through 04D. Native Chrome verified registration submission and the settings layout at a 390 px viewport. Chrome checks covered the journal, audit, voucher approval, day book and accepted quotation conversion to an approved order. Browser checks used synthetic data. GST settings and invoice draft screens are owner-only. Native browser checks on the draft screens remain pending. Its first targeted run failed because the synthetic quote fixture omitted mandatory pricing fields. After adding them, all seven focused tests passed.

## Reconciliation, security and release gates

- Local tests verify exact journal and voucher balance, company isolation, duplicate submission protection, locked-period behavior and immutability guards for sealed journals. Order tests exercised CSRF and PDF data boundaries. Invoice draft tests exercised owner access, cross-company sources, duplicate drafts, procurement data exclusion in sales snapshots and absence of ledger posting.
- Three fictional companies completing a full financial month have not been simulated. Inventory-to-ledger, GST-to-ledger and bank-to-ledger reconciliations remain pending.
- PostgreSQL triggers and concurrent financial writes require execution on a dedicated synthetic PostgreSQL instance before production. The SQLite guards cover normal application database access. Database administrators with schema privileges retain broader control.
- Statutory invoicing is a release blocker. Review company and counterparty registrations, sourcing and effective dates, place of supply, tax treatment, document numbering and rounding with an Indian accounting professional. The internal GST calculator has no default rate and the invoice draft service has no issuance or filing interface. See [GST compliance notes](GST_COMPLIANCE.md).
- No deployment, remote push, live financial data or live government submissions occurred.

## Files and migrations

- Instructions and planning in `AGENTS.md`, `docs/checkpoints/`, the tracker, the handoff, the overnight progress file and accounting architecture, test and security documents.
- Accounting core changes in `accounting/` and `templates/accounting/`, including migrations `0003_journal_sealed`, `0004_accounting_guards` and `0005_alter_journal_kind_voucherdraft`.
- Operational orders in `orders/` and `templates/orders/`, with order migrations 0001 and 0002, plus Django configuration, workspace navigation and the quote detail entry point.
- GST settings, calculation and internal draft preparation in `invoicing/`, with migrations `0001_initial` and `0002_invoicedraft`, plus accounting navigation, `templates/invoicing/` and the GST source register. The migrations were exercised on disposable test databases.

See the [tracker](ACCOUNTING_CHECKPOINTS.md) for granular progress and the [handoff](ACCOUNTING_HANDOFF.md) for implementation commits. [Overnight progress](OVERNIGHT_PROGRESS.md) contains exact restart commands.
