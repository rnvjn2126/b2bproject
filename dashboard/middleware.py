from django.utils.cache import add_never_cache_headers
from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin

from .accounts import business_account_for
from .billing import current_plan, user_has_seat


class PlanAccessMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        if not request.user.is_authenticated or not match or match.namespace != "dashboard":
            return None
        account = business_account_for(request.user)
        reason = ""
        if match.url_name in {"reports", "company_defaults", "product_csv_import"} and current_plan(account)["tier"] == "free":
            reason = "This feature is included in Small, Medium and Large Business plans."
        elif request.method not in {"GET", "HEAD", "OPTIONS"} and match.url_name != "preferences" and not user_has_seat(request.user, account):
            reason = "Your workspace is over its user allowance. You can still view and export records; ask the owner to upgrade or adjust the team."
        if reason:
            return render(request, "billing/limit.html", {"reason": reason}, status=403)


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
