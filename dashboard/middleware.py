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
        return response
