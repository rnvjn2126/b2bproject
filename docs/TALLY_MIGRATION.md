# Tally migration

The local owner pilot accepts a reviewed subset of Tally XML and prepared Excel workbooks. Enable the pilot in a loopback development instance with `DJANGO_INTERNAL_TALLY_IMPORT=1`. Open **Accounts → Tally migration** after setting up the target financial year and chart.

## Verified formats

| Source | Verified in this application |
| --- | --- |
| Tally XML | `ENVELOPE` with `TALLYMESSAGE` records for groups, ledgers, catalogue stock items and accounting-only sales, purchase, receipt and payment vouchers. The signed amounts follow the official example, with debit negative and credit positive. |
| Prepared Excel | XLSX containing one or more of the **Groups**, **Ledgers**, **Stock Items**, and **Vouchers** worksheets. Incoming headings can be mapped to these fields. |
| Tally JSON | TallyPrime added JSON import in Release 7.0. This pilot requires XML or prepared Excel. |

The file exchange shape follows the official [XML request and response examples](https://help.tallysolutions.com/article/DeveloperReference/integration-capabilities/case_study_1.htm) and [current XML, JSON and Excel format guidance](https://help.tallysolutions.com/import-data-from-xml-or-json/). Tests use synthetic data and an isolated SQLite database. Live TallyPrime compatibility needs a licensed synthetic test installation using the intended release and company settings.

## Prepared Excel columns

- **Groups** — Name, Parent.
- **Ledgers** — Name, Parent. Optional Opening Balance, Email, Phone and Address.
- **Stock Items** — Name, Base Units. Use kg, tonne, metre or piece and keep opening stock quantities outside this import.
- **Vouchers** — Date, Voucher Type, Voucher Number, Ledger Name. Use signed Amount or separate positive Debit and Credit columns. Optional GUID and Narration. Enter one row per voucher ledger line, with matching voucher fields across the group. Use ISO dates, compact YYYYMMDD dates or typed Excel dates.

Example field mapping:

```json
{"groups":{"Source Debtors":"ASSET-3"},"ledgers":{"Source Cash":"1000"},"columns":{"ledgers":{"name":"Ledger label"}}}
```

Group and ledger mappings target existing codes in the selected workspace. Source parents determine account classification. Imported debtor and creditor ledgers can create customer and supplier contacts. Existing contact details remain authoritative. Opening balances require one balanced opening journal with distinct target ledgers in an open period. Chart-only imports can omit the opening date.

## Review and confirm

1. Split masters and vouchers into reviewed files if needed. Each file is limited to 512 KiB and 500 records or Excel rows. Multiple imports can reuse identical records.
2. Preview with a date and any mappings. The preview runs the normal posting validations in a rolled-back transaction. It reports the first invalid source record or ledger mapping.
3. Re-upload the same file when confirming. The fifteen-minute token binds the file, mappings, opening date, user and workspace. Validation repeats inside the commit transaction. One invalid record rolls back the entire batch.
4. Check the import history and opening journal. Compare the trial balance and day book with the source reports. The audit stores file and record digests and posting references separately from the source file bytes.

The parser rejects destructive actions, malformed XML and DTDs. The shared XLSX safety checks reject macros, external links, formulas, spreadsheet errors and oversized expanded archives. Invoice tax, bill, bank, cost-centre or inventory allocations and nonzero stock openings require separate review. Accounting-only vouchers use the existing journal rules. They create no statutory invoices or physical stock movements.

## Export and future transport

The owner can download sealed, unreversed sales, purchase, receipt and payment vouchers in Tally XML form. Opening balances and referenced ledgers need to be prepared on the receiving side. The synthetic round trip was tested both into a second workspace and back into the source workspace, where exported journal identities prevent duplicate posting.

Future Tally transport can supply a bounded document and its format to the same parser and confirmation service. Keep transport authentication, endpoint configuration and live credentials outside the import core. Require an explicit source-company mapping and an independently reviewed dry run before applying data from a live connection. JSON, live synchronisation and vendor-side compatibility are outside the verified pilot.
