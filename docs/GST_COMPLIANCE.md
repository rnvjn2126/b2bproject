# GST compliance work

GST computation, GST filing exports and government submissions are outside Phase 1. Quotation tax fields are estimates and are not invoice tax records. Before implementing Phase 3, review current primary sources from CBIC and the GST portal and record rule versions, effective dates and professional decisions. Keep e-invoicing and e-way bill submission separate from internal posting.

Initial source register (27 November 2026):

- [CBIC CGST Rules, Rule 46](https://cbic-gst.gov.in/pdf/cgst-rules-18042018.pdf) identifies invoice fields and financial-year numbering. This is an older compilation. Check subsequent amendments and applicable notifications before shipping an invoice as a tax invoice.
- [GST Portal GSTR-1 guide](https://tutorial.gst.gov.in/userguide/returns/Creation_of_Outward_Supplies_Return_in_GSTR-1.htm) and [HSN Table 12 advisory](https://tutorial.gst.gov.in/downloads/news/updated_advisory_hsn_table12_25042025.pdf) inform how we capture item classifications and distinguish B2B from B2C. Confirm the applicable schema at implementation time.
- [GST Portal GSTR-3B manual](https://tutorial.gst.gov.in/userguide/returns/Create_and_Submit_GSTR3B.htm) separates liability reporting from filing and payment. Our internal accounting reports will need reconciliation before either step.
- [GST Portal GSTR-2B FAQ](https://tutorial.gst.gov.in/userguide/returns/FAQ_gstr2b.htm) describes the portal's supplier-derived input tax credit statement. Preserve imported records separately and reconcile them against purchase postings.
- [Official e-Way Bill documentation](https://docs.ewaybillgst.gov.in/) is a starting point for transport document integration. Recheck current applicability when designing dispatch.

Open reviews include registration and place-of-supply mappings, rate effective dates, input credit treatment, reverse charge, exports/SEZ, GSTR-2B data matching and electronic document applicability. No universal steel rate or statutory threshold is configured.

## Checkpoint 04A · Calculation scope

- IGST Act sections 7, 8 and 10 define inter-state and intra-state supplies and several place-of-supply scenarios for goods. The calculator accepts an explicitly determined domestic place of supply. The supplier GSTIN prefix and a destination alone cannot determine all scenarios. [India Code, Integrated Goods and Services Tax Act](https://upload.indiacode.nic.in/showfile?actid=AC_CEN_2_2_00043_201713_1517807328116&filename=a2017-13.pdf&type=actfile)
- The inclusive-price formula is based on Rule 35. The internal calculator rounds components to paise and preserves the entered inclusive total. Confirm document-level and statutory rounding, cess treatment and tax base against applicable current rules before issuing invoices. [CBIC consolidated CGST Rules, January 2022](https://cbic-gst.gov.in/pdf/01012022-CGST-Rules-2017-amended_Part-A.pdf)
- Invoice and note requirements and electronic invoice applicability need a separate review against amended rules and current notifications for each company. GSTIN validation here checks the regular registration format only. Registration status and ownership require independent confirmation. [CBIC invoice rules](https://cbic-gst.gov.in/gst-invoice-rules.html) · [GST e-invoice portal guidance](https://einvoice6.gst.gov.in/content/e-invoice-printing-process-mandatory-fields-modes-of-irn-generation/)

The calculation module supports company-specific, dated HSN/SAC rates, one domestic GST regime per line, percentage cess and rounding. It contains no statutory rate seed data. GST rates, place of supply, party registration, tax treatment and rules for rounding, discounts, freight, returns and notes require approval before production use.

## Checkpoint 04B · Internal invoice drafts

One confirmed dispatch or goods receipt can seed one owner-only draft. The dispatch uses the sales order price. The receipt uses the purchase order price as an estimate. Rate selection uses the movement date. Confirm the legally relevant tax time, actual supplier invoice amount, registered parties, treatment of partial deliveries, credit/debit notes and returns before adding statutory issuance. Draft snapshots preserve the inputs and results but are not issued invoice records. The current service has no UI, print, issuance or journal path.

## Checkpoint 04C · Draft settings

Accounting owners can add draft registration records and dated rates. The settings capture a source URL as text and use the calculation module's supported range and classification rules. Recording a source is an audit aid. Verify its relevance, effective period and the applicable commodity classification before statutory use.

## Checkpoints 04E–04F · Proposed journal lines

The invoice posting service currently computes balanced proposals and validates ledger mappings without issuing an invoice or posting accounting entries. Explicit purchase input-tax treatment in a proposal represents an accounting choice for testing. Establish the legal entitlement, treatment of partial recovery, actual purchase invoice value and posting policy before connecting this to a user-facing issue action.

### Internal issuance implementation boundaries

1. In one transaction, lock the company, confirm the draft and exact ledgers are in that company, and find an open accounting period for the approved issue/posting date. Recheck order eligibility and financial limits.
2. Generate a unique workspace and financial-year issue reference. Keep external purchase references distinct. Store the issue date, revision-free snapshot, selected treatment, actor and source draft. Repeated submissions should converge on the same issued record and sealed journal.
3. Add invoice-specific posting validation in the shared engine. Existing manual trade vouchers continue to enforce their current account rules. A failure in validation, numbering, persistence or journal sealing must roll back the whole issue operation.
4. Guard issued records and their journal relationship against updates and deletions through normal application and database writes. Handle corrections through linked reversal and note workflows. Verify SQLite migration triggers and run PostgreSQL integration tests when available.
5. Keep these operations internal while sale numbering, supplier document dates/references and input-tax eligibility are being verified. Do not route public invoice output or GST filings through an unreviewed implementation.

## Checkpoint 04G · Gated internal sales issuance

The internal service posts one confirmed dispatch snapshot and one journal. Its reference uses the workspace financial-year series. A caller must confirm the total and use the dispatch date as the internal accounting date. The workflow stays disabled by default and has no issue button or external output. This accounting date and reference do not establish the statutory timing or number of a tax invoice. Confirm issue timing, registered-person numbering series, print fields and electronic invoicing before introducing any statutory action. [CBIC invoice rules](https://cbic-gst.gov.in/gst-invoice-rules.html) · [CBIC sectoral guidance on invoicing](https://cbic-gst.gov.in/hindi/sectoral-faq.html?ld=SDINSOADirect)

Use a later purchase slice to validate the supplier's actual document date, number and amount. The preparatory purchase estimate uses the purchase order price. When the supplier amount differs, preserve explicit actual amounts and require review before journal posting. [CBIC input-tax credit rules](https://cbic-gst.gov.in/input-tax-credit-rules.html)

## Checkpoint 04H · Gated internal purchase recording

Purchase drafts can capture the actual supplier unit price and supplier invoice date. The supplier date selects the configured rate version for the internal estimate. An owner must confirm the total, reference and input-tax treatment before internal posting. The system retains the supplier document separately from the internal financial-year reference and treats the supplier reference as case-insensitive within the supplier GSTIN and financial year. One internal record currently covers one confirmed receipt. Confirm how to match invoices covering multiple receipts, partial credits and purchase adjustments before wider use.

The internal accounting date cannot precede the receipt or supplier document. Neither an entered supplier document nor the selected input-tax treatment proves GST input-credit eligibility. Verify the supplier document and applicable eligibility conditions before connecting this to a tax workflow. [India Code, CGST Act section 16](https://upload.indiacode.nic.in/showfile?actid=AC_CEN_2_2_00042_201712_1517807328102&filename=a2017-12.pdf&type=actfile)

## Checkpoint 04J · Internal return adjustments

A sales return creates an internal credit adjustment; a purchase return creates an internal debit adjustment. The service apportions the original journal by returned quantity and rounds against cumulative quantity so a complete return reverses the original amounts. Returns and whole-invoice cancellations are mutually exclusive. The current records are financial, with no stock movements and no filing output. Very small quantities that produce no positive financial adjustment need a combined accounting adjustment or a future stock-only return path.

Section 34 explains supplier credit and debit notes, including returns, and sets conditions on liability adjustments. Internal purchase debit adjustments do not replace required supplier documents. Review note particulars, tax impact, original source documents, report treatment and deadlines before enabling statutory output. [India Code, CGST Act section 34](https://upload.indiacode.nic.in/showfile?actid=AC_CEN_2_2_00042_201712_1517807328102&filename=a2017-12.pdf&type=actfile)
