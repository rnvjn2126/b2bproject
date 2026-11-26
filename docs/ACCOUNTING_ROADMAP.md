# Native accounting roadmap

The baseline at 5b38dca has Django workspaces, owner/manager/sales roles, billing entitlements, steel catalogue and quotation workflows. Quotation tax inputs, supplier landed cost and sales reports are operational data. There is no chart, general ledger, recognised revenue, inventory ledger or statutory filing. The latest Steel Quotes branch includes billing and reports absent from the older development branch.

| Phase | Work | Acceptance gate |
| --- | --- | --- |
| 1 | Chart, ledgers, dates and dimensions, immutable posted journals, reversals and trial balance | Balanced postings, permission and lock tests, reversal reconciliation |
| 2 | Voucher workflow, order conversion, sales and purchase invoices, customer and supplier accounts | Unique document conversions, partial quantity controls, issued snapshots |
| 3 | Versioned GST rules, GSTIN/HSN, invoice and note tax handling, reconciliations | Current official requirements, rounded totals, accountant approval of statutory mappings |
| 4 | Bank/cash books, payment allocations, ageing, imports and reconciliation | Partial payments, duplicate detection, matched statement reconciliation |
| 5 | Steel stock movements, heat/lot, warehouses, cutting, scrap and costing | Concurrent stock constraints and inventory-to-ledger reconciliation |
| 6 | Financial statements, owner dashboard, drilldowns and exports | Posted-data reconciliation, month simulation and financial equation |
| 7 | Tally interoperability and migration | Supported samples, mapped preview, dry run, atomic apply and reconciled opening balances |
| 8 | TDS/TCS, assets, year-end closing, localisation and release readiness | Official rules and review, PostgreSQL concurrency, restore drills and financial security review |

Each milestone requires Django checks, migration drift check, full tests, security/integrity review and a verified feature branch commit. Existing quotation acceptance never posts revenue. Decide the initial document numbering, approval roles, valuation policy, tax treatment and statutory rollout with the business and accountant as each becomes relevant.
