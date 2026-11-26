# Checkpoint 14: Final integration testing and security review

Read the previous handoff and apply the permanent instructions before starting.

Avoid unnecessary features. Simulate a full financial month for each fictional stainless trader, steel distributor and multi-warehouse stockist. Include enquiries, quotes, orders, receipts and stock, invoices and GST, partial/outstanding payments, returns/credit notes, bank reconciliation and expenses. Reconcile trial balance, balance sheet, stock quantity and ledger valuation, party balances, configured tax and reports. Verify no duplicate posting, silent changes, unauthorised data or tenant crossover. Run authorised defensive local checks of OWASP risks, object-level access, injection, XSS, CSRF, privilege escalation, uploads, spreadsheets, concurrency, exports and financial logic. Fix confirmed issues and rerun tests. Run full suite and configuration checks. Document results, scope, blockers, security, reconciliation, changed files, migrations and production readiness in `docs/ACCOUNTING_FINAL_REPORT.md`. No zero-vulnerability or statutory certification claims.

Run relevant automated tests, the full regression suite, Django system checks and migration drift checks. Record actual results, risks and open decisions, commit locally and update the tracker and handoff before starting the next checkpoint.
