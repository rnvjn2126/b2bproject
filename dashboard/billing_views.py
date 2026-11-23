import hashlib
import hmac
import json
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .accounts import business_account_for
from .billing import PLANS, apply_billing_event, current_plan, paid_periods, reserved_seats, used_quotations
from .forms import WorkspaceSignupForm
from .models import BusinessAccount, SubscriptionPeriod


def sandbox_available():
    return settings.DEBUG and settings.BILLING_SANDBOX_ENABLED


@require_GET
def plans(request):
    account = business_account_for(request.user) if request.user.is_authenticated else None
    return render(request, "billing/plans.html", {
        "plans": [{"tier": tier, **details} for tier, details in PLANS.items()],
        "plan": current_plan(account),
        "is_billing_owner": not account or request.user.pk == account.owner_id,
        "sandbox": sandbox_available(),
    })


@require_http_methods(["GET", "POST"])
def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")
    if not settings.PUBLIC_SIGNUP_ENABLED:
        return render(request, "billing/signup_closed.html", status=403)
    form = WorkspaceSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
            BusinessAccount.objects.create(owner=user, name=form.cleaned_data["company_name"])
        login(request, user, backend="dashboard.backends.PasswordPolicyBackend")
        messages.success(request, "Your Free workspace is ready. No payment is needed.")
        return redirect("dashboard:home")
    return render(request, "billing/signup.html", {"form": form})


@login_required
@require_GET
def billing_overview(request):
    account = business_account_for(request.user)
    owner = account.owner if account else request.user
    is_owner = owner.pk == request.user.pk
    return render(request, "billing/overview.html", {
        "account": account, "plan": current_plan(account), "is_billing_owner": is_owner,
        "used": used_quotations(account, owner),
        "seats": 1 + account.memberships.count() if account else 1,
        "reserved_seats": reserved_seats(account) if account else 1,
        "history": account.subscription_periods.all()[:30] if account and is_owner else [],
        "upcoming": paid_periods(account).filter(starts_at__gt=timezone.now()).order_by("starts_at") if account else [],
        "sandbox": sandbox_available(),
    })


@login_required
@require_POST
def checkout_create(request):
    if not sandbox_available():
        raise PermissionDenied("Live payments are not enabled. No money has been taken.")
    tier, months = request.POST.get("tier"), request.POST.get("months")
    if tier not in SubscriptionPeriod.Tier.values or months not in {"1", "12"}:
        return HttpResponse("Choose a valid plan and billing period.", status=400)
    account = business_account_for(request.user, create=True)
    if account.owner_id != request.user.pk:
        raise PermissionDenied("Only the company owner can manage billing.")
    with transaction.atomic():
        BusinessAccount.objects.select_for_update().get(pk=account.pk)
        pending = account.subscription_periods.filter(status="pending").first()
        if pending and (pending.tier != tier or pending.months != int(months)):
            pending.status = SubscriptionPeriod.Status.CANCELLED
            pending.save(update_fields=["status"])
            pending = None
        purchase = pending or SubscriptionPeriod.objects.create(account=account, tier=tier, months=int(months))
    return redirect("dashboard:checkout", pk=purchase.pk)


@login_required
@require_http_methods(["GET", "POST"])
def checkout(request, pk):
    purchase = get_object_or_404(SubscriptionPeriod, pk=pk, account__owner=request.user)
    if request.method == "POST":
        if not sandbox_available() or not purchase.is_test:
            raise PermissionDenied("Payment simulation is available only in local development.")
        outcome = request.POST.get("outcome")
        if outcome not in {"paid", "failed", "refunded"}:
            return HttpResponse("Choose a valid test outcome.", status=400)
        apply_billing_event({"id": str(uuid.uuid4()), "purchase_id": str(purchase.pk), "outcome": outcome})
        messages.success(request, "Test billing event recorded. No money was charged or refunded.")
        return redirect("dashboard:billing")
    return render(request, "billing/checkout.html", {"purchase": purchase, "sandbox": sandbox_available()})


@login_required
@require_POST
def cancel_checkout(request, pk):
    purchase = get_object_or_404(SubscriptionPeriod, pk=pk, account__owner=request.user)
    with transaction.atomic():
        BusinessAccount.objects.select_for_update().get(pk=purchase.account_id)
        SubscriptionPeriod.objects.filter(pk=purchase.pk, status="pending").update(status="cancelled")
    messages.info(request, "Unpaid checkout cancelled. Existing prepaid access is unchanged.")
    return redirect("dashboard:billing")


@csrf_exempt
@require_POST
def test_webhook(request):
    # Local integration contract, NOT a Razorpay/live payment endpoint.
    secret = settings.BILLING_WEBHOOK_SECRET
    if not sandbox_available() or len(secret) < 32:
        return HttpResponse(status=503)
    body = request.body
    if len(body) > 16_384:
        return HttpResponse(status=413)
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected.encode(), request.headers.get("X-Steel-Quotes-Signature", "").encode()):
        return HttpResponse(status=403)
    try:
        apply_billing_event(json.loads(body))
    except (ValidationError, ValueError, TypeError):
        return HttpResponse("Invalid billing event.", status=400)
    return JsonResponse({"received": True})
