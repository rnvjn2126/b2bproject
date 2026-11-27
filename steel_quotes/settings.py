"""Settings for the local steel quotation MVP."""
import os
import re
import secrets
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
debug_value = os.environ.get("DJANGO_DEBUG", "true").strip().lower()
if debug_value not in {"1", "true", "yes", "0", "false", "no"}:
    raise ImproperlyConfigured("DJANGO_DEBUG must be true or false.")
DEBUG = debug_value in {"1", "true", "yes"}
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY when DJANGO_DEBUG is disabled.")
    SECRET_KEY = secrets.token_urlsafe(50)
if not DEBUG and (
    len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5
    or SECRET_KEY.startswith("django-insecure-") or SECRET_KEY != SECRET_KEY.strip()
):
    raise ImproperlyConfigured("Use a randomly generated DJANGO_SECRET_KEY of at least 50 characters.")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]",
    ).split(",")
    if host.strip()
]
if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Wildcard ALLOWED_HOSTS is not allowed.")
if not DEBUG:
    if not os.environ.get("DJANGO_ALLOWED_HOSTS") or not ALLOWED_HOSTS:
        raise ImproperlyConfigured("Set explicit DJANGO_ALLOWED_HOSTS in production.")
    # Exact DNS hostnames only: no URLs, ports, wildcard or subdomain patterns.
    if any(not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*", host)
           or len(host) > 253 for host in ALLOWED_HOSTS):
        raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must contain exact DNS hostnames without schemes or ports.")

SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 3600 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
# Native form submissions need their origin for Django's CSRF check.
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "axes",
    "dashboard",
    "accounting",
    "orders",
    "invoicing",
    "settlements",
    "banking",
    "inventory",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "dashboard.middleware.PrivateResponseMiddleware",
    "dashboard.middleware.PlanAccessMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "dashboard.backends.PasswordPolicyBackend",
]
REQUIRE_STRONG_LOGIN_PASSWORDS = not DEBUG
# Apply lockout to each username/IP pair; production workers need a shared database.
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_USE_ATTEMPT_EXPIRATION = True
AXES_LOCKOUT_PARAMETERS = [["ip_address", "username"]]
# Do not trust client-supplied forwarding headers. A future proxy must supply
# a verified REMOTE_ADDR through the application server, not arbitrary headers.
AXES_IPWARE_META_PRECEDENCE_ORDER = ("REMOTE_ADDR",)
AXES_RESET_ON_SUCCESS = True
AXES_ENABLE_RETRY_AFTER_HEADER = True

ROOT_URLCONF = "steel_quotes.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "dashboard.context_processors.workspace_preferences",
    ]},
}]
WSGI_APPLICATION = "steel_quotes.wsgi.application"
ASGI_APPLICATION = "steel_quotes.asgi.application"

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
if not DEBUG:
    required_database_variables = (
        "DJANGO_DB_NAME", "DJANGO_DB_USER", "DJANGO_DB_PASSWORD", "DJANGO_DB_HOST", "DJANGO_DB_SSLROOTCERT",
    )
    missing = [name for name in required_database_variables if not os.environ.get(name, "").strip()]
    if missing:
        raise ImproperlyConfigured("Production PostgreSQL configuration is missing: " + ", ".join(missing))
    if not Path(os.environ["DJANGO_DB_SSLROOTCERT"]).is_file():
        raise ImproperlyConfigured("DJANGO_DB_SSLROOTCERT must point to the database CA certificate file.")
    database_port = os.environ.get("DJANGO_DB_PORT", "5432")
    if not database_port.isascii() or not database_port.isdecimal() or not 1 <= int(database_port) <= 65535:
        raise ImproperlyConfigured("DJANGO_DB_PORT must be between 1 and 65535.")
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DJANGO_DB_NAME"],
        "USER": os.environ["DJANGO_DB_USER"],
        "PASSWORD": os.environ["DJANGO_DB_PASSWORD"],
        "HOST": os.environ["DJANGO_DB_HOST"],
        "PORT": database_port,
        "OPTIONS": {"sslmode": "verify-full", "sslrootcert": os.environ["DJANGO_DB_SSLROOTCERT"]},
    }}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "login"

# Local simulation only. Live billing needs a separately reviewed provider integration.
BILLING_SANDBOX_ENABLED = DEBUG
BILLING_WEBHOOK_SECRET = os.environ.get("BILLING_TEST_WEBHOOK_SECRET", "")
# Public signup needs email verification and abuse controls before a hosted launch.
PUBLIC_SIGNUP_ENABLED = DEBUG

# Internal issue requires review before it can be exposed to business users.
INTERNAL_INVOICE_ISSUANCE = False
