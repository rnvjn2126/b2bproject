# Accounting completion and verification checklist

The 19 numbered sections and final implementation instruction are tracked below. **Complete** means the entire item is implemented. Verification requires a review of the whole item's deliverables. Run 1 records acceptance against the applicable specifications. Run 2 repeats verification independently, with changed test order or a different scenario or environment when appropriate. A passing test of one feature does not complete a broader item. Documentation and process items use review checks in place of software tests.

| # | Item | Implementation | Verification | Run 1 | Run 2 |
| --- | --- | --- | --- | --- | --- |
| 1 | Repository assessment, roadmap, branch | Complete | Branch, baseline, roadmap and GitHub push confirmed | Review complete | Branch and roadmap rechecked |
| 2 | Core accounting engine | Partial | Balanced posting, locks, period reports, reversals and SQLite duplicate handling verified. Document posting and broader opening workflows remain open. | Subset passed | Full item open |
| 3 | Indian chart of accounts | Partial | Starter and custom chart verified. Complete hierarchy and party mappings open. | Subset passed | Full item open |
| 4 | Vouchers | Partial | Journal, receipt, payment and contra verified. Other voucher types, configurable numbers, approval and attachments open. | Subset passed | Full item open |
| 5 | Quotation conversion workflow | On hold | Quotation acceptance leaves the ledger unchanged. Orders and purchasing held at owner's direction. | Acceptance boundary passed | Full item on hold |
| 6 | GST | Research | Source register exists. Versioned rules, GST documents and reconciliation remain open. | Open | Open |
| 7 | Sales and purchase invoicing | On hold | No new invoicing work in this milestone. | On hold | On hold |
| 8 | Receivables and payables | Pending | Party allocations, credit controls and ageing remain open. | Open | Open |
| 9 | Banking and cash | Partial | Starter cash and bank vouchers verified. Bank rules, statements, matching and reconciliation remain open. | Subset passed | Full item open |
| 10 | Steel inventory | Pending | Stock posting, lot and heat tracking, cutting, costing and reconciliation remain open. | Open | Open |
| 11 | Financial reports | Partial | Trial balance, general ledger, balance sheet and P&L verified. Remaining reports, exports and full financial month verification open. | Reporting milestone passed, 121 tests | Reporting milestone passed, 121 tests in reverse order |
| 12 | Financial dashboard | Pending | Owner dashboard and its data sources remain open. | Open | Open |
| 13 | Tax and statutory architecture | Pending | TDS, TCS, asset register, closing, carry-forward and professional review remain open. | Open | Open |
| 14 | Tally migration | Research | Official format sources recorded. Import, export, matching and round trips remain open. | Open | Open |
| 15 | Accounting security | Partial | Owner access, scoping, locks, reversal history and CSRF exercised. Finance roles, tamper evidence, secure storage and recovery remain open. | Subset passed | Full item open |
| 16 | User experience | Partial | Accounts navigation, forms, filters and mobile trial balance verified. Shortcuts, search, saved filters, printing and localisation remain open. | Subset passed | Full item open |
| 17 | Testing | Partial | Phase 1 and first voucher tests, Chrome and SQLite concurrency checks complete. Full-month simulation and PostgreSQL checks open. | Subset passed | Full item open |
| 18 | Phased implementation | In progress | Accounting foundation and cash vouchers pushed as verified milestones. Standalone reporting is proceeding while sales and purchasing are on hold. | Per milestone | Per milestone |
| 19 | Development rules and docs | Ongoing | Seven requested documents maintained. Feature branch and synthetic data verified. | Per milestone | Per milestone |
| 20 | Implement and continue after verification | Ongoing | Foundation and cash vouchers delivered. Proceed with independent reporting and controls. | Per milestone | Per milestone |

Executed results and their scope belong in [Accounting test results](ACCOUNTING_TEST_RESULTS.md). The implementation sequence and acceptance gates are in the [roadmap](ACCOUNTING_ROADMAP.md).
