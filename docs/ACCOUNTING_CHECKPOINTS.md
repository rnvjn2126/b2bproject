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
| 06 | Banking and reconciliation | Partial. Company funds accounts, transfers and books passed both 187-test suites. Manual references and cheque history passed both 190-test suites. CSV preview and staging passed both 194-test suites. Excel, reconciliation and owner screens remain open. |
| 07 | Steel inventory | Assigned. Depends on catalogue units and order movement references |
| 08 | Inventory valuation and procurement | Assigned. Depends on verified stock and ledger movements |
| 09 | Financial reporting | Assigned. Existing core statements; additional reports depend on posted data from earlier checkpoints |
| 10 | Tally migration and interoperability | Assigned. Depends on stable accounting, voucher and stock import targets |
| 11 | Customer acquisition | Assigned. Reuses quote constraints, catalogue and company branding |
| 12 | Advanced accounting and taxation | Assigned. Depends on reconciled invoices, ledgers and official sources |
| 13 | Permissions, experience and performance | Assigned. Builds on existing authentication and workspace membership |
| 14 | Final integration and security review | Assigned. Full-month scenarios require verified earlier modules |

Apply checkpoints in sequence. If an upstream checkpoint remains incomplete, record the condition explicitly before advancing dependent work. An explicit prompt authorizes the named checkpoint; it does not authorize publishing, deployment or financial actions.
