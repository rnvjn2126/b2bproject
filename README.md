# Steel quotation MVP

Local Django 5.2 application for the steel-trader quotation MVP.

## Windows quick start

From PowerShell in this folder:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\start-local.bat
```

Open <http://127.0.0.1:8000/>. Create a local account in a second terminal with:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

The workspace dashboard includes a private, account-scoped checklist for adding the first customer, supplier, product, enquiry, and quotation.

## Shared team workspace

The business owner can name the workspace and create a one-time invitation link for a teammate. Links expire in 72 hours; the app stores only a digest and does not email invitations. Teammates must use the invited email. Owners alone manage member roles and access. Owners and managers can approve below-floor quotations and edit pricing guardrails; sales members can work in the shared company records but cannot perform those actions. This is a local MVP control, not a production identity or compliance certification.

Owners and managers can review selected workspace activity, including quote approvals and status changes, pricing changes, and membership changes. Entries do not store rates, margins, invitation emails, or user-entered notes. This application history is not tamper-evident.

The SQLite database is created locally as `db.sqlite3`. Do not use this development configuration for deployment.

Review [compliance readiness](docs/COMPLIANCE_READINESS.md) before using real customer data or hosting the service. It records the current app boundary and India-specific operator responsibilities; it is not a legal certification.

## Security configuration

Local development defaults to `DEBUG=True`, binds to loopback in `start-local.bat`, and generates a fresh secret key when the server starts. Login locks out a username/IP pair after five failed attempts in a rolling 15-minute window. Sessions expire after eight hours and when the browser closes. Signed-in users can change passwords, and sign-out requires a CSRF-protected POST. For production, set `DJANGO_DEBUG=false`, provide a private high-entropy `DJANGO_SECRET_KEY`, and set `DJANGO_ALLOWED_HOSTS` to the exact hostnames before starting Django. Production mode redirects to HTTPS and enables secure session/CSRF cookies and one-hour HSTS. HSTS subdomain and browser-preload policies remain off until the real domain and every subdomain are confirmed. Never commit secrets. See [the security review](docs/SECURITY_REVIEW.md) for the tested controls and remaining launch work.

## Follow-ups and catalogue CSV

Use **Follow-ups** to review open reminders. Each enquiry can have dated reminders, and a staff member marks them complete manually. WhatsApp opens only from the explicit link on an enquiry and never sends a message automatically.

Customer, supplier, product, enquiry, quote, and follow-up lists support case-insensitive search and paginate in groups of 25. Enquiries and quotes can be filtered by status; follow-ups can show open, completed, or all reminders.

The **Products** page supports importing and exporting the product catalogue. CSV uses the headers `name, grade, shape, dimensions, unit, weight_basis, weight_kg, notes`; imports are validated as a whole before saving and exports include only the signed-in user's products. Customer contacts and supplier rates are not included.

## Development checks

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test --noinput
```

## Click-to-run checks on Windows

After creating the `.venv` environment above, double-click **`test-local.bat`**
in File Explorer. It runs the Django configuration check, verifies that no
model migrations are missing, and runs the Django test suite. A clear
`[PASS]` or `[FAIL]` message will appear. This does not require the overnight
controller or Codex CLI.

The test suite covers workspace isolation and role permissions, invitations,
onboarding progress, searchable and paginated lists, unit normalization,
supplier offer coverage, landed-cost and gross-margin arithmetic, quote PDF
permissions, manual follow-ups, and safe catalogue CSV exports. These are
automated regression tests, not a substitute for a buyer acceptance test.

**Current security boundary:** record access is scoped to the account owner, with invited teammates using the same company workspace. Sales and managers currently see company-wide records; branch and representative-level restrictions are not implemented. Production rollout still requires the operational and legal controls in the linked readiness documents.
