# Accounting checkpoints

Local branch: `ai/accounting-overnight`. Baseline: `c9659aa490d51902cb214925cfdf973d4f5f0bb8` from `ai/steel-accounting`.

The [numbered specifications](checkpoints/) define each checkpoint's scope. A checkpoint passes only when its required functionality, documentation and verification are complete. Tests of existing or partial functionality do not complete a checkpoint. Record the first and second full runs separately. Use the [handoff](ACCOUNTING_HANDOFF.md) to resume and the [20-item checklist](ACCOUNTING_CHECKLIST.md) for prior project scope.

| # | Checkpoint | Status |
| --- | --- | --- |
| 00 | Repository preparation | Complete. Django check and migration drift check passed. Runs 1 and 2 each passed 121 tests. |
| 01 | Double-entry accounting engine | Complete on the supported local SQLite workflow. Both full runs passed 123 tests. PostgreSQL execution remains a release gate. |
| 02 | Ledgers and voucher management | Complete for internal vouchers. Both full runs passed 125 tests. Statutory invoices and tax notes remain in Checkpoint 04. |
| 03 | Sales and purchase orders | Complete for operational orders and confirmed movement records. Both full runs passed 131 tests. |
| 04 | Invoicing and Indian GST | Partial. Owner GST settings, versioned calculations and the internal draft workflow are implemented. The draft screens passed 17 focused tests, both 142-test suites and Chrome verification. Posting proposals and ledger mapping passed both 147-test suites. Gated sales and purchase posting, cancellation and return adjustments passed both 160-test suites. Branded private A4 print passed both 162-test suites. Gated owner issue and correction controls passed both 165-test suites. Statutory release and non-return notes are blocked pending professional decisions. |
| 05 | Receivables, payables and payments | Partial. Due dates, ageing, immutable payments and allocation/release passed both 175-test suites. Credit settings and reviewed MSE dates passed both 178-test suites. Private statements and reminder drafts passed both 181-test suites. Settlement operation forms passed both 184-test suites. Complete for the internal pilot. Release gates remain. |
| 06 | Banking and reconciliation | Complete for the gated local pilot. Both 202-test suites and Chrome checks passed. |
| 07 | Steel-specific inventory | Complete for the gated local pilot. Both final runs passed 223 tests. Chrome, a populated SQLite migration upgrade and two-thread stock probes passed. Work paused by request. |
| 08 | Inventory valuation and procurement | Complete for the gated local pilot. Valuation, cost journals, procurement, late charges, cutting and scrap verified. Both full runs passed 261 tests. PostgreSQL and production accounting approval remain release gates. |
| 09 | Financial reporting | Complete for local owner reporting. Ledger-based dashboard, statements, registers, analysis and private PDF, Excel and CSV downloads verified. Both full runs passed 270 tests. |
| 10 | Tally migration and interoperability | Active. Verify supported TallyPrime formats before implementing bounded, staged imports. |
| 11 | Customer acquisition | Assigned. Reuses quote constraints, catalogue and company branding |
| 12 | Advanced accounting and taxation | Assigned. Depends on reconciled invoices, ledgers and official sources |
| 13 | Permissions, experience and performance | Assigned. Builds on existing authentication and workspace membership |
| 14 | Final integration and security review | Assigned. Full-month scenarios require verified earlier modules |

Apply checkpoints in sequence. If an upstream checkpoint remains incomplete, record the condition explicitly before advancing dependent work. An explicit prompt authorizes the named checkpoint; it does not authorize publishing, deployment or financial actions.
