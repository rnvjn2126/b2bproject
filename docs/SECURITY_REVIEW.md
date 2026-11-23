# Security review

## Controls implemented

- Require an environment-provided high-entropy `DJANGO_SECRET_KEY` and explicit allowed hosts when `DEBUG` is disabled. Development uses a random key per process and no wildcard host.
- Production settings enable HTTPS redirects, secure and HTTP-only session cookies, secure CSRF cookies, one-hour HSTS, content-type sniffing protection, a no-referrer policy, and frame denial. HSTS subdomain and preload remain off until the actual domain is confirmed.
- Django password validators enforce similarity, common-password, numeric-password, and 12-character minimum checks. Authenticated users can change their passwords; sessions are limited to eight hours and expire when the browser closes. Logout is a CSRF-protected POST.
- django-axes blocks a username/IP pair after five failed logins, with a 15-minute cooldown extended by further failures and returns `429` with `Retry-After`.
- CSRF protects state changes. The app scopes customer, supplier, product, enquiry, offer, quote, follow-up, pricing, PDF, and CSV access to the company owner account. Invited teammates share that account's records; owner and manager roles control pricing changes and quote approvals, while only owners manage membership.
- Team invitations use a high-entropy one-time bearer token whose SHA-256 digest is stored, expire after 72 hours, are email-bound, require the signed-in email for existing accounts, and can be revoked by the owner. Invitation delivery is manual; the app sends no email.
- Owners and managers can view an account-scoped activity history of quote approvals/status changes, pricing guardrail changes, and team access changes. Entries omit rates, margins, invitation emails, and free-text notes.
- CSV imports validate the entire file before writing and cap files at 1 MB / 500 rows. Product, customer, and supplier exports are account-scoped, escape formula-like cells, and send `Cache-Control: no-store`; contact exports are labelled as sensitive business data.
- Customer quotes omit procurement prices and margins. Quote pages and PDFs reject records owned by another account, and the PDF is labelled as not a tax invoice.

## Regression checks

- Missing CSRF token returned `403` without changing the enquiry; a valid token succeeded.
- An untrusted `Host` returned `400` in production-mode configuration.
- Fifth bad login from a username/IP pair returned `429`; the correct password remained blocked for that pair, while another user from another IP could log in.
- Password change used Django validation and kept the current user signed in. `GET` logout returned `405`; CSRF-protected `POST` signed out.
- Existing tests cover multiple users, shared workspace boundaries, sales/manager permissions, invitation acceptance and revocation, activity history, quote pricing and approval, supplier comparisons, PDF confidentiality, follow-ups, and CSV constraints and exports.

## Verification status

The counts below record earlier checkpoints. See the 23 November production-hardening results at the end for the current changes.

- `manage.py check`: passed.
- `manage.py makemigrations --check --dry-run`: passed; no missing model migrations.
- `manage.py test dashboard.test_security --noinput`: passed, 8 tests.
- `manage.py test dashboard.test_teams --noinput`: passed, 8 tests covering invitations, membership, shared data, activity history, and role boundaries.
- `manage.py test dashboard.test_reports --noinput`: passed, 3 tests covering company scoping, calculated rates, and empty states.
- `manage.py test dashboard.test_exports dashboard.test_reports dashboard.tests.ProductCSVTests --noinput`: passed, 12 tests across three export/report suites.
- `manage.py test --noinput`: passed, 76 tests across multiple synthetic users and records.
- Production-mode `manage.py check --deploy` reported only `security.W005` and `security.W021`, because HSTS subdomain coverage and browser preload are intentionally disabled pending domain confirmation.

## Remaining launch work

- Confirm the production hostname, HTTPS-only subdomains, TLS proxy, forwarded client-IP behavior, and shared production database. Axes' default database handler depends on a shared durable database across workers.
- The shared workspace currently gives all invited teammates company-wide record visibility. Branch- and salesperson-level restrictions and a tamper-evident activity log are not implemented.
- The activity history is an application feature, not a tamper-evident security log or a substitute for legally required infrastructure log retention.
- Configure secret storage, encryption/key management, backups, monitoring, and secure India-based infrastructure logs. Application tests do not verify provider operations.
- Assign privacy and incident-response owners; review retention, notice/rights handling, subprocessors, processor contracts, incident reporting, and tax treatment with Indian counsel and a chartered accountant.
- Do not use the local SQLite configuration or quotation PDF as a production tax-invoice service.

No deployment was performed. This review is not a penetration test, legal opinion, tax certification, or guarantee against fines.

## Production hardening, 23 November 2026

- Fixed the startup enforcement gaps: missing/weak production keys and missing/malformed host allowlists now raise configuration errors. The previous text overstated what was enforced.
- Fixed the Axes OR-versus-pair configuration mismatch. Forged forwarding headers are ignored; the lockout test now also verifies that another user on the same office IP can sign in.
- Production rejects weak existing passwords at normal and admin login, including credentials set through scripts. Local demo credentials remain local and must be reset before release.
- Added no-store/private cache headers to application responses, no-referrer, Permissions-Policy and HTML CSP. Moved enquiry item JavaScript to the existing static script so CSP does not break dynamic rows.
- Added PostgreSQL configuration with certificate/hostname verification and fail-closed WSGI/ASGI defaults. No production database was created, accessed or migrated.
- See [production security and release gates](PRODUCTION_SECURITY.md) for the remaining infrastructure, privileged-access and operational checks.

### Executed verification for this milestone

- Security/configuration suites: 15 tests passed.
- Full suite: 90 tests passed in 139.133 seconds after fixing the invitation session regression and cache-header assertion uncovered in the first run.
- `manage.py check`: no issues. `makemigrations --check --dry-run`: no changes.
- `check --deploy` using synthetic production configuration: only W005/W021, intentionally pending HSTS subdomain/preload decisions. No live PostgreSQL/TLS connection was tested.
- `pip check`: no broken requirements. `pip-audit` against the complete 12-package installed runtime snapshot: no known vulnerabilities; no packages skipped. The audit tool lives in a separate local environment and is not an application dependency.
- Headless Chrome: actual login, quote pricing preview/save and PDF response, mobile navigation and enquiry row additions, tablet/desktop layouts, theme/text/motion preferences, no-store/no-referrer headers, and blocked inline-script injection passed. Visually inspected the mobile enquiry screenshot.
