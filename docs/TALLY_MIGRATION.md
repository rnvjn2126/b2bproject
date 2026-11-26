# Tally migration

The native accounting app does not require Tally or copy its implementation. Interoperability is planned for Phase 7. Validate official supported export formats and versions with synthetic fixtures. Require a mapping preview, duplicate and balance checks, auditable atomic import and opening balance reconciliation before enabling import. Treat voucher, item, ledger and tax matching as distinct tasks.

Tally's [data export reference](https://help.tallysolutions.com/data-management/export-data-in-tally/) lists master and voucher exports and identifies XML and JSON among the supported formats. Its [master and transaction walkthrough](https://help.tallysolutions.com/how-to-export-import-entire-data-masters-transactions-to-a-new-company/) separates the two. Start with versioned XML fixtures for both, and validate round-trip compatibility in a licensed test installation before offering export back to Tally. Native JSON support depends on the release.
