# Decisions, Assumptions, and Morning Questions

## Default decisions for autonomous MVP
- Build for India, INR, metric units; start with stainless round bars and sheets, but design catalogue for additional shapes.
- Start with order-based trading, not inventory accounting.
- Use Django 5.2 LTS, SQLite development database, server-rendered responsive pages, local synthetic data.
- Default target gross margin 12%; **demonstration assumption only**, configurable per business. Quotes below threshold require explicit manager review.
- Show entered weights and calculated weights separately; never infer missing grade/density without a visible assumption.
- Never send customer communication automatically. All WhatsApp links require a user click.
- A shared company workspace is available to the owner and invited teammates; sales and managers see the same company records, while owner-only controls manage membership.
- Keep purchase rates, margins and internal remarks off customer-facing documents.

## Record each new decision
| Date | Task | Decision | Rationale | Reversible? |
|---|---|---|---|---|
| 2026-11-22 | Initial setup | Choose safe defaults listed above | Permit unattended work without pretending business rules are confirmed | Yes |
| 2026-11-22 | Django foundation | Use Django's built-in session authentication; provision local accounts with `createsuperuser` or Django admin; no public sign-up | Keeps the local demo access-controlled without introducing account approval or recovery workflows | Yes |
| 2026-11-22 | Catalogue milestone | Customers, suppliers and products are owned by the signed-in local user; products capture optional metric dimensions and distinguish actual from theoretical item weight without calculating or inferring weight | Establishes a clear ownership boundary and avoids unverified steel-density assumptions | Yes |
| 2026-11-22 | Supplier landed-cost comparison | Record offers against one enquiry line with an entered unit rate, available quantity, delivery days, freight total and packaging/incidental total. Normalize kg and tonnes directly; allow piece conversion only from the linked catalogue product's recorded actual or theoretical kg per piece, saved with the offer as its conversion basis. Allocate freight and packaging across the smaller of requested and available quantities after conversion, and label partial coverage. | Makes comparisons transparent without inferring missing weights or assuming an offer covers the full order | Yes |
| 2026-11-22 | Supplier landed-cost comparison | Treat supplier rates and entered freight/packaging as entered amounts, with no supplier GST calculation in this milestone | GST inclusion and any non-creditable procurement tax treatment need business confirmation | Yes |
| 2026-11-22 | RFQ intake | Capture enquiry channel, received/required dates, customer, notes and one or more requested items; permit a catalogue product or free-text specification, with quantity required in an explicit catalogue metric unit | Supports varied incoming enquiry detail without inferring steel weights or adding supplier/quote workflows | Yes |
| 2026-11-22 | Margin-protected quotations | Use account-editable defaults of 12% target margin, 8% minimum margin, and 5% maximum discount for the local demo. Calculate selling price from landed cost using gross margin (not markup), apply any discount to that target price, require one full-quantity offer per enquiry line, and snapshot the inputs and calculated rates on each quote. Round unit prices to four decimals and displayed INR totals to paise using half-up rounding. A below-floor or negative-margin quote remains pending until a signed-in staff account explicitly approves it. The approval action stays within the existing per-user account boundary; shared multi-user manager review needs the business account model and role hierarchy confirmed first. | Makes the arithmetic auditable and prevents a quote from silently bypassing the configured discount cap or review floor; these thresholds and the manager role are unconfirmed pilot assumptions | Yes |
| 2026-11-22 | Customer quotation documents | Assign a local quote number from the creation year and record ID; revisions retain that number and increment their revision. New quotes default to a seven-day validity period. Apply the entered GST/tax percentage to the sales subtotal only; do not certify tax treatment. The PDF uses the configured shared workspace name, or the demo Steel Quotes identity if it has not been set; it includes customer-facing specifications, selling rates, tax and terms, and excludes supplier names, procurement rates and margin details. Quotes pending margin review cannot be downloaded. | Keeps the pilot document useful while seller contact details, tax treatment and commercial terms await confirmation; avoids exposing internal procurement data | Yes |
| 2026-11-22 | Follow-ups and hardening | Attach dated reminders to enquiries; staff mark completion manually. Use enquiry states New, In progress and Closed, and quote states move through Ready/Approved, Sent, then Accepted/Lost (Expired only after the validity date). New quotes default to seven days of validity, which remains an editable assumption. WhatsApp links appear only for valid phone formats, open with an explicit staff click, and do not prefill or send a message. Product CSV import/export uses a fixed eight-column catalogue schema, validates all rows before an atomic import, is scoped to the signed-in owner, caps uploads at 1 MB / 500 rows, and prefixes spreadsheet formula-like exported cells with an apostrophe. | Provides local follow-up tracking and controlled data portability without background messaging, supplier rates, customer contacts, or cross-account exports | Yes |
| 2026-11-22 | Security review | Generate a random development secret key; require `DJANGO_SECRET_KEY` and explicit allowed hosts with debug disabled; enable HTTPS redirect, secure cookies and one-hour HSTS in production mode; set a 12-character minimum with Django's built-in password validators; rotate the weak local demo admin credential. Keep HSTS subdomain/preload flags off until the real domain and all subdomains are confirmed. | Removes default-key, debug, weak-password and cookie/header risks while avoiding a long-lived HSTS policy for an unconfirmed domain | Yes |
| 2026-11-22 | Repository setup | Seed the empty `b2bproject` repository on an orphan `development` branch with the existing tested MVP; leave `main` untouched. | Honors the branch-only publishing constraint without adding a commit to `main` | Yes |
| 2026-11-22 | Security and compliance readiness | Limit login attempts with django-axes; mark generated quotation PDFs as not tax invoices; remind users to minimize personal data; document India-specific operator obligations and unresolved release checks. | Adds practical application safeguards without claiming that software alone certifies legal compliance | Yes |
| 2026-11-22 | Account safeguards | Expire sessions after eight hours and at browser close; use Django's password-change views and POST-only logout with CSRF protection. | Reduces exposure from unattended sessions while retaining standard Django account behavior | Yes |
| 2026-11-22 | List usability | Add case-insensitive search across customer, supplier, product, enquiry, quote, and follow-up lists; add status filters to enquiries/quotes and open/completed/all follow-up views; paginate lists in groups of 25. All results remain owner-scoped. | Keeps larger demo accounts navigable without weakening account boundaries | Yes |
| 2026-11-22 | First-run onboarding | Show a five-step dashboard checklist; calculate progress only from the signed-in user's own customer, supplier, product, enquiry, and quote records. | Helps a new account reach the first value moment without loading fake data into a real workspace | Yes |
| 2026-11-22 | Growth research | Position the initial product around enquiry-to-quote workflow; document separate small, midsize, and enterprise needs. Do not set pricing or claim integrations, certification, or market outcomes without evidence. | Keeps acquisition hypotheses aligned with delivered capabilities and avoids false launch claims | Yes |
| 2026-11-22 | Shared company workspace | Keep domain records owned by the company's owner account; invited users share all company records. Owners alone invite, remove, or change team roles; owners and managers approve below-floor quotations and edit pricing guardrails. Invitations are one-time, expire after 72 hours, store only a token digest, and require the invited email. | Adds practical team access and approval controls without rewriting existing ownership data or granting sales users pricing authority | Yes |
| 2026-11-23 | Workspace activity history | Record the actor and affected record ID for quote approvals/status changes, pricing guardrail changes, and invitation/membership changes. Keep entries generic and account-scoped; do not copy prices, margins, invitation emails, or notes. Show history to owners and managers only. | Makes high-impact team decisions reviewable while limiting exposure of commercial and personal data | Yes |
| 2026-11-23 | Business reports | Show a company-wide quotation status count, accepted/(accepted + lost) win rate, overdue open reminders, and reminder completion and enquiry counts for a rolling 30-day period. Do not display sales totals, supplier costs, or margin data. | Gives teams a basic operational view without turning this MVP into financial or accounting reporting | Yes |
| 2026-11-23 | Contact data export | Provide owner-scoped customer and supplier CSV exports with contact fields, formula escaping, and no-store response headers; exclude quotation pricing and supplier rates. | Supports customer-controlled data portability while reducing cache and spreadsheet formula risks | Yes |

## Questions for the next morning review
1. Should the first demo focus on stainless steel only or include MS/alloy products?
2. Are supplier offers for stock on hand or procurement after an order?
3. What target and minimum gross margins, maximum discount, and manager-approval hierarchy should be used?
4. Which quotation terms and GST treatments apply to your business?
5. Should future branches or sales representatives have more restricted visibility than the shared company workspace?
6. Do supplier offer prices include GST, and should any non-creditable GST enter landed procurement cost?
7. Should unprefixed ten-digit phone numbers always be treated as Indian numbers when opening WhatsApp?
8. Are the selected quotation outcomes and follow-up reminder fields sufficient for the pilot pipeline?
9. What legal company name, logo, seller address/contact details, GST registration, and quotation language should appear on customer PDFs?
10. What production hostname and subdomains will be HTTPS-only, and which trusted TLS proxy will terminate HTTPS and provide the client IP to login throttling?
11. Who will own the privacy contact, data retention schedule, incident response, India-based log storage, GST configuration, and any required data-processor contracts for the hosted service?

Questions do not block unrelated safe implementation. Never fabricate an answer; mark the relevant workflow as a configurable pilot assumption.

## Blockers
None at setup. Record any task failure with failing command, log, and recommended next action.

## User answers to confirm later
- Shared company workspace with company-wide record visibility; the owner and managers approve below-margin quotations. The owner alone manages membership.

## Demo workflow decisions (23 November 2026)
- The requested overnight branch was absent from GitHub. Its starting point is the published UI commit 4dad58d. The existing topbar account and mobile navigation menus are the overlays identified in that revision.
- Dashboard counts use the latest revision in each quotation chain. Pending covers ready, under review, approved and sent. Accepted and lost are staff-recorded outcomes. An accepted quotation is the endpoint of this MVP; sales orders and invoicing are separate future work.
- Estimated pipeline value is the sum of pending selling line totals before tax. Margin is weighted by selling value; an empty denominator displays a dash. Only owners and managers see these dashboard figures. Estimates are unweighted by probability.
- Rank full-coverage offers per requested item, including ties. Customer history shows enquiries and revisions; supplier history shows submitted offers. Neither represents settled payments or purchases.
- Dark mode follows the device setting. Customer preview displays the same protected PDF as the download. Pricing preview is internal and saves no quotation.
- Confirm whether expired-but-unclosed offers belong in forecasts and whether management needs separate won-order tracking before a commercial pilot.

## Personal and company customisation (23 November 2026)
- My preferences stores theme (device/light/dark), text size (16/18/20 px), comfortable/compact spacing and reduced motion against the signed-in user. Reset restores defaults for that user. Browser zoom remains available. Device reduced motion always wins.
- Company defaults are shared within the workspace and editable by owners and managers. Validity is limited to 1–365 days, and terms to 2,000 characters each. Their changes are recorded in workspace activity without copying the text.
- New quotation forms start with the company's validity and payment/delivery terms. Staff may edit these before saving. Existing quotation terms remain stored on the quote, and revisions inherit their source terms. Revision validity keeps the existing seven-day default.
- No company tax default was added because applicable GST depends on the transaction. The existing quote-specific tax input and pricing guardrails remain the controls for that workflow.
- Future options to review with the owner include company logos and seller details, preferred catalogue units, and configurable dashboard shortcuts.

## Production hardening (23 November 2026)
- Production startup rejects missing/weak secret keys, missing host allowlists and host patterns/URLs. The key checks match Django's minimum length/diversity criteria; they cannot prove randomness. Generate a new secret with a cryptographic generator for the future deployment.
- Corrected Axes configuration from username OR IP to the documented username/IP pair. Trust only REMOTE_ADDR; ignore forwarded headers until a real proxy topology is configured and tested. Distributed attacks still need infrastructure rate limits.
- Application responses prohibit caching and send same-origin referrers. The original no-referrer policy caused native browser sign-in forms to send a null origin, which Django rejected. Referrers remain suppressed on external requests.
- Production login enforces existing Django password validators even for credentials created through scripts. The local demo login remains available; it must be reset with manage.py changepassword before production use. No password was silently changed and no production data was accessed.
- First hardening milestone: 14 security/configuration tests passed; Django reported no system-check issues.
- Production requires PostgreSQL with verify-full TLS and a trusted CA file. The future infrastructure's certificates, connectivity, least-privilege roles and concurrent transactions are not validated by local SQLite tests.
- WSGI/ASGI default to a production settings module which refuses debug mode. The CLI and loopback demo retain local settings. No infrastructure was created and no deployment was performed.
- CSP blocks inline and off-origin scripts; the enquiry row handler moved into the existing JavaScript file. Inline styles remain allowed for Django admin compatibility. Chrome confirmed that injected inline JavaScript is blocked and existing workflow interactions still work.
- The first full run found three failures: an export test assumed an exact header string, and two invitation tests exposed an old backend reference. Corrected the assertion to require no-store/private and fixed the actual invitation sign-in reference; all 90 tests passed on rerun.
- The 12 installed runtime packages passed pip-audit with no known advisories on 23 November 2026. The audited versions are recorded in requirements-production.lock; target-OS verification, future re-audits and OS/server patching remain release duties.
- Release questions remain in docs/PRODUCTION_SECURITY.md: production domain/proxy, PostgreSQL provider, administrative MFA/SSO, infrastructure limits, backup/restore and monitoring owners. No unsupported answers were invented.

## Daily workspace report (26 November 2026)
- Reports defaults to today's activity in India time and accepts past dates. Counts use enquiry received dates and recorded timestamps for quotation saves, sends, outcomes and completed follow-ups. Revisions count as saves, and “marked sent” reflects what staff recorded.
- Daily activity is a company-wide Business-plan report. It does not measure individual logins, time spent or staff performance. Decide later whether those measures or scheduled delivery are needed.

## Tiered plans (23 November 2026)
- Add Free, Small Business, Medium Business and Large Business as company-wide plans. Provisional user limits are 1/3/10/30; monthly quotation-save limits are 5/100/500/2,000. All paid tiers expose the same existing business features with different capacity.
- Prices remain unset. No real payment keys, provider registration, charges, customer messages or deployments are used. The local simulation is prominently labelled and cannot grant access in production.
- Monthly quota counts all successful quotation saves including revisions, not previews. Usage resets at the India calendar-month boundary and is not reset by changing plan.
- Pending invitations reserve seats. After expiry, excess members become read-only; the owner and existing data/exports remain available. Security and accessible display settings are not paid features.
- Renewals and tier switches begin after prepaid access ends. Monthly/annual terms are calendar-based. Immediate upgrades, proration, automatic renewals and partial refunds await business rules.
- Initial targeted billing tests exposed two fixture errors (protected event cleanup and a consumed invitation session token), then three new quote tests exposed a missing required supplier lead time in their fixture. Corrected the fixtures; all 17 billing/quotation-limit tests passed.
- Outstanding commercial questions: prices/taxes, final quotas, immediate upgrade policy, fair-use/storage limits, refunds and the actual payment provider. Production signup additionally needs verified identity and abuse controls.
- See docs/BILLING.md for precise feature boundaries and the local test webhook contract.

## Contractual credit and MSE deadline tracking

- Credit defaults count calendar days from the internal sales posting date or the supplier's invoice date. Applying a default records a due date for that invoice. Changing a party default does not rewrite existing due dates. The customer credit warning totals positive posted exposures and flags past-due amounts separately. It does not offset unassigned funds before a staff allocation.
- The MSE deadline workflow requires an owner's explicit eligibility and acceptance-date review with an evidence reference. For the covered scenarios, it records the earlier of a written due date and acceptance plus 45 days, or acceptance plus 15 days where there is no written agreement. It keeps contractual dates separate from the MSE tracking date. [India Code, MSMED Act sections 2(b) and 15](https://www.indiacode.nic.in/bitstream/123456789/19412/1/msme_act_2006.pdf)
- Review actual eligibility and documentary evidence with a qualified adviser, especially for distributors, wholesalers and retail traders. Udyam registration alone does not establish eligibility for this workflow. Interest, tax deductions, disclosures and disputes are out of scope for the calculator. [Ministry of MSME registration FAQs](https://www.ideas.msme.gov.in/Ministry-of-MSME/skills%2Cloan%2Ccredit_guarantee%2CPM-atmnirbhar-Economic-Package%2Celigibility_criteria%2Cguidelines_Schemes/query_questions_FAQs.htm)

## Internal bank statement staging

The current CSV source format is UTF-8 with columns `date,reference,description,debit,credit` in that order. Use ISO calendar dates, INR rupees with at most two decimal places, and one positive amount column. Debit means the bank reports an outflow. Credit means the bank reports an inflow. Imports are bounded to 256 KB and 1,000 rows.

A preview confirmation binds the file bytes to one bank account. Identical files replay the existing batch. For overlap, compare date, normalized reference, direction and amount. Include description when a reference is missing. Review ambiguous repeated rows in a single file. Cross-file overlap requires explicit confirmation to skip known entries. Stored statement lines stage reconciliation evidence without posting journals or independently verifying that a payment settled.
