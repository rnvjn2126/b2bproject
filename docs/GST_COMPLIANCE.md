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
