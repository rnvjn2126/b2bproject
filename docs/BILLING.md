# Workspace plans and billing preview

Status: implemented locally with simulated payments. No real checkout, gateway account, recurring debit, financial refund or tax invoice is enabled.

## Provisional plan catalogue

| Plan | Users including owner | Quotation saves per calendar month |
| --- | ---: | ---: |
| Free | 1 | 5 |
| Small Business | 3 | 100 |
| Medium Business | 10 | 500 |
| Large Business | 30 | 2,000 |

All plans include the existing catalogue, enquiries, supplier comparisons, protected quotation calculations/PDFs, follow-ups, personal accessibility preferences and data exports. Business plans additionally enable team capacity, the existing Reports page, company-default editing and product CSV import. Existing role restrictions still apply; paying never grants a salesperson manager/owner permissions.

The catalogue is defined in dashboard/billing.py. Prices are deliberately unset pending owner confirmation; the UI says “Pricing pending”. There are no invented discounts or implicit promises of unlimited capacity.

## Access and usage rules

- Each company shares one entitlement and quota. The owner alone manages billing. Teammates can see their plan/usage but not the owner's billing history or checkout records.
- Every saved quotation, including a revision, counts. Previews and invalid/rolled-back saves do not count. The monthly counter persists independently of quote deletion and is initialized from existing quotations where necessary.
- Quota months use Asia/Kolkata calendar boundaries, regardless of monthly/annual payment term. An upgrade or renewal never resets usage.
- The account row is locked when allocating quotes, seats or access periods. Quota allocation also uses a conditional database increment. Local SQLite tests verify boundaries/rollback; real simultaneous PostgreSQL requests must still be tested before launch.
- Valid pending invitations reserve seats. Acceptance rechecks current capacity, so an invitation created before expiry cannot restore excess access.
- When access expires or its simulated payment is refunded, effective access is recomputed on the next request. No background task is required.
- Excess teammates retain read/export access but cannot modify shared business records. Seats go to the owner, then the earliest memberships. The owner can remove members; no membership or trading record is deleted automatically.
- Saved company defaults remain attached to historical records and can continue pre-filling quotes; editing them requires a Business plan.
- Quotation exports and core security are never held behind a payment gate. Reports are a Business feature.

## Local walkthrough

1. Open /plans/ to compare all four tiers, or /signup/ to create a synthetic Free workspace.
2. From the sidebar choose Plan & billing to see current usage and available seats.
3. As the owner, choose a Business tier and Monthly or Annual, then open its test checkout.
4. Simulate a failed or successful payment. Only a confirmed success grants access.
5. Use billing history to reopen a confirmed checkout and simulate a full refund.
6. Renewals and tier changes start after all prepaid periods end. Calendar-month arithmetic handles month ends and leap years. No immediate prorated upgrade or automatic debit is implemented.
7. Unpaid checkouts can be cancelled. To return to Free after prepaid access ends, do not renew. Existing paid periods are not silently cancelled or refunded.

Both payment simulation and test entitlements require DEBUG and BILLING_SANDBOX_ENABLED. They are unavailable in production, even if test records are copied into the production database. Public signup defaults off in production until identity/abuse controls are implemented.

## Test webhook contract

POST /billing/webhooks/test/ is exclusively a sandbox endpoint, not a Razorpay-compatible webhook or real provider integration.

For automated local integration tests, set BILLING_TEST_WEBHOOK_SECRET to a private random value of at least 32 characters. Send a JSON object with id (unique event ID), purchase_id (an existing test checkout UUID), and outcome (paid, failed or refunded). Sign the exact request bytes with HMAC-SHA256 and send the hexadecimal digest in X-Steel-Quotes-Signature.

The endpoint rejects invalid signatures and malformed events. Event IDs and canonical payload hashes prevent duplicate grants and conflicting replays. Failed events cannot overwrite confirmed access; cancelled/refunded orders cannot be reactivated by delayed success. Only minimal event metadata is retained. CSRF is exempted only for this signed endpoint; all interactive billing actions require CSRF-protected POSTs.

## Before real billing

- Confirm prices, taxes, allowances, invoicing requirements, cancellation/refund policy and whether upgrades should be immediate/prorated.
- Choose and integrate an actual provider (Razorpay was discussed, not configured). Use its exact event schema and server-side order/amount/currency/payment-status verification; never treat this generic sandbox webhook as a provider endpoint.
- Test provider-signed sandbox callbacks, duplicate/out-of-order delivery, reconciliation after missed events, refund/dispute states, and account/provider-ID mapping.
- Add production signup email verification, abuse limits and account-recovery flows before opening registration.
- Verify concurrent checkout, seat and quota requests on PostgreSQL.
- Automatic recurring subscriptions, partial refunds, prorated upgrades, real receipts/tax invoices and real checkout are not implemented.
- Follow the separate production security and compliance release gates. Nothing was deployed or charged by this milestone.
