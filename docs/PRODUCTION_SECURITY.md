# Production security and release gates

The application has not been deployed. These are preparation instructions, not a declaration that the service is ready for public use.

## Implemented application controls

- Startup rejects missing/short/low-diversity/insecure-prefix production keys, missing host allowlists, wildcard/subdomain patterns, URLs and ports in production host entries. Key checks cannot prove entropy: generate a fresh random key with `secrets.token_urlsafe(50)` in the approved secret-management workflow.
- Production requires PostgreSQL with a database hostname, user, password, database name and CA certificate file. Connections use `sslmode=verify-full`; SQLite remains for local development only.
- WSGI and ASGI default to `steel_quotes.production`, which refuses debug mode. The local CLI continues to use `steel_quotes.settings`. Setting an alternative settings module explicitly is an operator responsibility.
- HTTPS redirect, secure session/CSRF cookies, HTTP-only sessions, SameSite=Lax, one-hour HSTS, same-origin referrers, frame denial and MIME sniffing protection.
- All application responses prohibit storage in caches, including HTML, exports, PDF, login and logout. Static files are separate.
- HTML Content Security Policy permits scripts from the same origin, blocks inline scripts/event handlers, external scripts, framing, plugins and cross-origin form submissions. Inline styles remain allowed for Django admin widget compatibility. PDFs retain their normal browser preview behavior.
- Login throttles username/IP pairs after five failures. Only `REMOTE_ADDR` is used; changing `X-Forwarded-For` cannot reset the counter. This is not protection against all distributed attacks.
- Production login applies Django password validators to existing accounts too. A script-created weak demo account cannot authenticate to the normal login or admin. Use `manage.py changepassword USERNAME` through an authorized administrative environment to recover; never put passwords in command arguments or Git.

## Environment and commands

Use `.env.example` as a list of required variables. It deliberately contains no working secrets and is not automatically loaded. `DJANGO_DB_SSLROOTCERT` is an absolute path to the trusted database CA certificate provided through the future infrastructure setup; a placeholder file will not establish a real connection.

In an isolated staging environment with synthetic data, after supplying the real environment securely:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-production.lock
.\.venv\Scripts\python.exe manage.py check --deploy --settings=steel_quotes.production
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=steel_quotes.production
```

Database migrations, static collection and starting a production WSGI/ASGI service belong to a separately authorized deployment. `start-local.bat` and `manage.py runserver` are only for local use. Do not point tests or the local demo at the production database.

`requirements-production.lock` records all 12 installed runtime dependency versions audited on Windows/Python 3.13 on 23 November 2026. `pip-audit` found no known vulnerabilities. It is a version snapshot, not a hash-verified cross-platform lock; verify installation and re-audit on the eventual hosting platform. `requirements-production.txt` retains compatible upgrade ranges for deliberate maintenance.

## Release gates still open

| Gate | Evidence required before release |
| --- | --- |
| Real PostgreSQL | Run migrations and functional/concurrency tests on an isolated PostgreSQL staging database; verify that invalid/untrusted certificates and mismatched hostnames fail. Local tests currently use SQLite. |
| HTTPS and proxy | Confirm domain/certificate, trusted ingress and network isolation of application workers. Configure and test how HTTPS and client IP reach Django. Do not trust forwarded headers from arbitrary clients. The current code deliberately does not enable `SECURE_PROXY_SSL_HEADER`. |
| Static assets and service | Choose a supported production server, run as an unprivileged account, collect and serve static assets, verify error pages and restart behavior. Never serve private database files or environment files. |
| Abuse and administrative access | Add and test edge request/body/concurrency limits and distributed-login protection. Decide on MFA/SSO for privileged users. Neither edge protection nor MFA is implemented here. |
| Credentials | Remove temporary preview administrator accounts before the final launch. Use a fresh production database and keep preview databases out of production. Verify that only approved administrators have access. Generate a fresh secret, use a least-privilege database user and test credential rotation. |
| Backups and operations | Configure encrypted backups, prove restoration, define retention, monitoring, alert delivery, incident ownership and access-controlled logs with suitable redaction. No infrastructure has been provisioned or verified. |
| Dependencies | Re-audit the pinned snapshot before release, verify it on the target platform, and establish patch/update ownership. The current 12-package snapshot passed pip-audit; this does not cover the OS, server or future advisories. |
| Privacy and legal review | Complete the business-specific items in COMPLIANCE_READINESS.md with qualified advisors. Software tests cannot certify compliance or guarantee that no fines will occur. |
| HSTS | Confirm all relevant subdomains before enabling includeSubDomains/preload. The two Django deployment warnings remain visible; they are not suppressed. |

Keep secrets out of Git and logs. Keep secret values out of support screenshots and diagnostic exports. No customer messages are sent by this application work.

## Verification boundaries

Configuration tests use generated synthetic secrets and a placeholder CA path; they do not contact PostgreSQL. HTTPS request tests use Django's simulated secure requests, not a live certificate. Local Chrome tests exercise browser CSP enforcement and the existing mobile/tablet/desktop workflow with synthetic data. These checks complement, but do not replace, deployment testing or an independent penetration test.

References: [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/), [Django proxy settings](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header), [Axes configuration](https://django-axes.readthedocs.io/en/stable/4_configuration.html).
