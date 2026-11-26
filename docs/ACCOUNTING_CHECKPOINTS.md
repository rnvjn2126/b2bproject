# Accounting checkpoints

Local branch: `ai/accounting-overnight`. Baseline: `c9659aa490d51902cb214925cfdf973d4f5f0bb8` from `ai/steel-accounting`.

The [numbered specifications](checkpoints/) define each checkpoint's scope. A checkpoint passes only when its required functionality, documentation and verification are complete. Tests of existing or partial functionality do not complete a checkpoint. Record the first and second full runs separately. Use the [handoff](ACCOUNTING_HANDOFF.md) to resume and the [20-item checklist](ACCOUNTING_CHECKLIST.md) for prior project scope.

| # | Checkpoint | Status |
| --- | --- | --- |
| 00 | Repository preparation | Complete. Django check and migration drift check passed. Runs 1 and 2 each passed 121 tests. |
| 01 | Double-entry accounting engine | Complete on the supported local SQLite workflow. Both full runs passed 123 tests. PostgreSQL execution remains a release gate. |
| 02 | Ledgers and voucher management | Complete for internal vouchers. Both full runs passed 125 tests. Statutory invoices and tax notes remain in Checkpoint 04. |
| 03 | Sales and purchase orders | Complete for operational orders and confirmed movement records. Both full runs passed 131 tests. |
| 04 | Invoicing and Indian GST | Partial. Versioned GST calculation verified in both 135-test runs. Invoice workflow and posting are open. |
| 05 | Receivables, payables and payments | Assigned. Depends on invoices and payment allocation semantics |
| 06 | Banking and reconciliation | Assigned. Depends on the ledger and payment workflows |
| 07 | Steel inventory | Assigned. Depends on catalogue units and order movement references |
| 08 | Inventory valuation and procurement | Assigned. Depends on verified stock and ledger movements |
| 09 | Financial reporting | Assigned. Existing core statements; additional reports depend on posted data from earlier checkpoints |
| 10 | Tally migration and interoperability | Assigned. Depends on stable accounting, voucher and stock import targets |
| 11 | Customer acquisition | Assigned. Reuses quote constraints, catalogue and company branding |
| 12 | Advanced accounting and taxation | Assigned. Depends on reconciled invoices, ledgers and official sources |
| 13 | Permissions, experience and performance | Assigned. Builds on existing authentication and workspace membership |
| 14 | Final integration and security review | Assigned. Full-month scenarios require verified earlier modules |

Apply checkpoints in sequence. If an upstream checkpoint remains incomplete, record the condition explicitly before advancing dependent work. An explicit prompt authorizes the named checkpoint; it does not authorize publishing, deployment or financial actions.
