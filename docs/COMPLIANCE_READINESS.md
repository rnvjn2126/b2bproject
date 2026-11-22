# India compliance readiness

**Reviewed 22 November 2026.** This local development application and readiness record are not legal or tax advice, a compliance certification, or a promise that use cannot result in a fine. Applicability depends on the operator, customer, data flows, hosting, turnover, and actual tax treatment. Review the intended service with Indian counsel and a chartered accountant before launch.

## Controls in this build

- Customer and supplier records are scoped to the signed-in account. Forms remind staff to store only authorised business contact details and avoid sensitive personal information.
- Business workspaces can store teammate account names and invitation email addresses. Invited sales and manager accounts share company-wide business records; only owners manage team membership. Invitations are manual, one-time, email-bound, revocable, and expire after 72 hours.
- Passwords use Django's similarity, common-password, numeric-password, and 12-character minimum checks. django-axes locks a username/IP pair after five failed attempts in a rolling 15-minute window and returns HTTP 429 with `Retry-After`.
- CSRF protection, secure production cookies, HTTPS redirect, host validation, content-type and framing headers, protected quotation PDFs, and owner-scoped exports are enabled or tested.
- Quotation PDFs say **QUOTATION ONLY - NOT A TAX INVOICE**. The app captures a user-entered tax percentage for a sales quotation; it does not determine tax classification, issue GST invoices, submit returns, or generate e-invoices.
- Development uses synthetic data and local SQLite. No production hosting, real customer data, GST registration details, or third-party processor is configured.

## Digital personal data

The app can store a contact's name, email, telephone number, address, and notes. Whether the trader, SaaS operator, or both act as Data Fiduciary for each use depends on who determines the purpose and means of processing; document those roles in contracts and obtain legal advice.

The DPDP Act commencement notification phases in substantive provisions in sections 3-17 and related duties 18 months after 13 November 2025, on **13 May 2027**. The Rules similarly phase in Rules 3 and 5-16, 18 months after publication; Rule 4 has a one-year commencement and Rules 1, 2, and 17-21 commenced on publication. The app is not DPDP-certified. Before production, provide required clear notices and a rights channel, identify a responsible privacy contact, define lawful purposes and retention/deletion, document processor contracts, and implement an incident process. Rule 6 describes safeguards including encryption, access control, monitoring, backups, and retaining relevant logs/data for one year; Rule 7 sets breach-intimation duties, including detailed Board information within 72 hours. Confirm exact obligations and dates with counsel.

## CERT-In and hosting operations

CERT-In's 28 April 2022 Directions are active. They require covered organisations and service providers to report listed cyber incidents within six hours, maintain secure ICT logs for a rolling 180 days within India, synchronize system clocks to approved NTP sources, and designate a point of contact. A Django setting cannot provide India-based log storage, time synchronization, incident monitoring, a six-hour response rota, or a designated CERT-In contact. Select hosting and operational providers, verify their locations and contracts, and assign these duties before launch.

## GST documents

The product prepares quotations only. CGST Act section 31 and CGST Rule 46 govern tax invoices for taxable supplies and their required particulars. The Invoice Registration Portal describes e-invoicing applicability for eligible taxpayers at aggregate annual turnover of Rs 5 crore or more in any financial year from 2017-18 onward, subject to the applicable notifications, exclusions, and entity conditions. The app does not issue invoices or e-invoices. Have a CA verify the business's GST registration, product classification, rates, place-of-supply treatment, invoice numbering, and e-invoice applicability before adding invoice workflows or using quote tax values.

## Release blockers for real data or public hosting

- Choose the production domain, trusted TLS proxy, database, encryption/key management, backups, and an India-based secure log-retention provider.
- Configure and test one-year personal-data/security log retention where required and CERT-In's active 180-day India-based ICT-log duty; do not use local SQLite or Axes lockout counters as a substitute for infrastructure logs.
- Publish a reviewed privacy notice and rights/grievance contact; decide lawful purposes, retention/erasure exceptions, access requests, and processor/subprocessor contracts.
- Assign a CERT-In point of contact and incident-response owner who can report applicable incidents within six hours and handle applicable DPDP notices.
- Obtain CA approval for quotation tax assumptions. Do not use this quotation PDF as a tax invoice.
- Decide whether the shared workspace's company-wide access is appropriate for each customer, supplier, and employee record before entering real data; per-branch and per-salesperson restrictions are not available.
- Re-check official laws, commencement notifications, GST notifications, and service-provider terms before launch; they can change.

## Official sources

- [Digital Personal Data Protection Act, 2023 (MeitY)](https://www.meity.gov.in/static/uploads/2024/02/Digital-Personal-Data-Protection-Act-2023.pdf)
- [DPDP Act commencement notification, G.S.R. 843(E), 13 November 2025 (Gazette of India)](https://egazette.gov.in/WriteReadData/2025/267647.pdf)
- [Digital Personal Data Protection Rules, 2025, G.S.R. 846(E) (Gazette of India)](https://egazette.gov.in/WriteReadData/2025/267650.pdf)
- [CERT-In Directions under section 70B, 28 April 2022](https://www.cert-in.org.in/PDF/CERT-In_Directions_70B_28.04.2022.pdf)
- [CGST Act section 31 (CBIC)](https://taxinformation.cbic.gov.in/content-page/explore-act/1000300/1000001/invoice/ACTS)
- [CGST Rules, Rule 46 (CBIC)](https://taxinformation.cbic.gov.in/content-page/explore-rules/1000136/1000001)
- [GST Invoice Registration Portal: e-invoice mandate](https://einvoice6.gst.gov.in/content/einvoice-mandate/)
