"""Production entry point; never silently enable the local demo configuration."""
from .settings import *  # noqa: F403

if DEBUG:
    raise ImproperlyConfigured("Production requires DJANGO_DEBUG=false.")
