# GST compliance work

GST computation, GST filing exports and government submissions are outside Phase 1. Quotation tax fields are estimates and are not invoice tax records. Before implementing Phase 3, review current primary sources from CBIC and the GST portal and record rule versions, effective dates and professional decisions. Keep e-invoicing and e-way bill submission separate from internal posting.

Initial source register (27 November 2026):

- [CBIC CGST Rules, Rule 46](https://cbic-gst.gov.in/pdf/cgst-rules-18042018.pdf) identifies invoice fields and financial-year numbering. This is an older compilation. Check subsequent amendments and applicable notifications before shipping an invoice as a tax invoice.
- [GST Portal GSTR-1 guide](https://tutorial.gst.gov.in/userguide/returns/Creation_of_Outward_Supplies_Return_in_GSTR-1.htm) and [HSN Table 12 advisory](https://tutorial.gst.gov.in/downloads/news/updated_advisory_hsn_table12_25042025.pdf) inform how we capture item classifications and distinguish B2B from B2C. Confirm the applicable schema at implementation time.
- [GST Portal GSTR-3B manual](https://tutorial.gst.gov.in/userguide/returns/Create_and_Submit_GSTR3B.htm) separates liability reporting from filing and payment. Our internal accounting reports will need reconciliation before either step.
- [GST Portal GSTR-2B FAQ](https://tutorial.gst.gov.in/userguide/returns/FAQ_gstr2b.htm) describes the portal's supplier-derived input tax credit statement. Preserve imported records separately and reconcile them against purchase postings.
- [Official e-Way Bill documentation](https://docs.ewaybillgst.gov.in/) is a starting point for transport document integration. Recheck current applicability when designing dispatch.

Open reviews include registration and place-of-supply mappings, rate effective dates, input credit treatment, reverse charge, exports/SEZ, GSTR-2B data matching and electronic document applicability. No universal steel rate or statutory threshold is configured.
