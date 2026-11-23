from django.utils.cache import add_never_cache_headers


class PrivateResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Every application page can contain account data, credentials or invite
        # tokens. Static assets are served separately and remain cacheable.
        add_never_cache_headers(response)
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if response.get("Content-Type", "").startswith("text/html"):
            # Django admin widgets use inline styles. Scripts must always come
            # from our origin; inline scripts and event handlers stay blocked.
            response.headers.setdefault("Content-Security-Policy", (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
                "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
            ))
        return response
