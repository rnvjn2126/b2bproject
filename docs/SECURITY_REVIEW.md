# Security review

## Controls implemented

- Require an environment-provided high-entropy `DJANGO_SECRET_KEY` and explicit allowed hosts when `DEBUG` is disabled. Development uses a random key per process and no wildcard host.
- Production settings enable HTTPS redirects, secure and HTTP-only session cookies, secure CSRF cookies, one-hour HSTS, content-type sniffing protection, a same-origin referrer policy, and frame denial. HSTS subdomain and preload remain off until the actual domain is confirmed.
- Django password validators enforce similarity, common-password, numeric-password, and 12-character minimum checks. Authenticated users can change their passwords; sessions are limited to eight hours and expire when the browser closes. Logout is a CSRF-protected POST.
- django-axes blocks a username/IP pair after five failed logins in a rolling 15-minute window and returns `429` with `Retry-After`.
- CSRF protects state changes. The app scopes customer, supplier, product, enquiry, offer, quote, follow-up, pricing, PDF, and CSV access to the signed-in owner.
- CSV imports validate the entire file before writing and cap files at 1 MB / 500 rows. Exports escape formula-like cells.
- Customer quotes omit procurement prices and margins. Quote pages and PDFs reject records owned by another account, and the PDF is labelled as not a tax invoice.

## Regression checks

- Missing CSRF token returned `403` without changing the enquiry; a valid token succeeded.
- An untrusted `Host` returned `400` in production-mode configuration.
- Fifth bad login from a username/IP pair returned `429`; the correct password remained blocked for that pair, while another user from another IP could log in.
- Password change used Django validation and kept the current user signed in. `GET` logout returned `405`; CSRF-protected `POST` signed out.
- Existing tests cover multiple users, ownership boundaries, quote pricing and approval, supplier comparisons, PDF confidentiality, follow-ups, and CSV constraints.

## Verification status

- `manage.py check`: passed.
- `manage.py makemigrations --check --dry-run`: passed; no missing model migrations.
- `manage.py test dashboard.test_security --noinput`: passed, 8 tests.
- `manage.py test --noinput`: passed, 56 tests across multiple synthetic users and records.
- Production-mode `manage.py check --deploy` reported only `security.W005` and `security.W021`, because HSTS subdomain coverage and browser preload are intentionally disabled pending domain confirmation.

## Remaining launch work

- Confirm the production hostname, HTTPS-only subdomains, TLS proxy, forwarded client-IP behavior, and shared production database. Axes' default database handler depends on a shared durable database across workers.
- Configure secret storage, encryption/key management, backups, monitoring, and secure India-based infrastructure logs. Application tests do not verify provider operations.
- Assign privacy and incident-response owners; review retention, notice/rights handling, subprocessors, processor contracts, incident reporting, and tax treatment with Indian counsel and a chartered accountant.
- Do not use the local SQLite configuration or quotation PDF as a production tax-invoice service.

No deployment was performed. This review is not a penetration test, legal opinion, tax certification, or guarantee against fines.
