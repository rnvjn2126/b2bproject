import calendar
import hashlib
import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import BillingEvent, BusinessAccount, MonthlyUsage, Quote, SubscriptionPeriod, TeamInvitation


# Provisional commercial allowances, never tax/pricing promises.
PLANS = {
    "free": {"name": "Free", "seats": 1, "quotations": 5},
    "small": {"name": "Small Business", "seats": 3, "quotations": 100},
    "medium": {"name": "Medium Business", "seats": 10, "quotations": 500},
    "large": {"name": "Large Business", "seats": 30, "quotations": 2000},
}


def paid_periods(account):
    periods = SubscriptionPeriod.objects.filter(account=account, status=SubscriptionPeriod.Status.PAID)
    if not (settings.DEBUG and settings.BILLING_SANDBOX_ENABLED):
        periods = periods.filter(is_test=False)
    return periods


def current_plan(account):
    now = timezone.now()
    period = paid_periods(account).filter(starts_at__lte=now, ends_at__gt=now).order_by("-starts_at").first() if account else None
    tier = period.tier if period else "free"
    return {"tier": tier, **PLANS[tier], "period": period}


def used_quotations(account, owner):
    month = timezone.localdate().replace(day=1)
    usage = MonthlyUsage.objects.filter(account=account, month=month).first() if account else None
    # Seed legacy records lazily so existing quotations cannot bypass the first limit.
    return usage.quotations if usage else Quote.objects.filter(owner=owner, created_at__date__gte=month).count()


def reserve_quotation(account):
    """Call inside the same transaction as the quote save; failures roll back usage."""
    plan = current_plan(account)
    month = timezone.localdate().replace(day=1)
    usage, _ = MonthlyUsage.objects.get_or_create(
        account=account, month=month,
        defaults={"quotations": used_quotations(account, account.owner)},
    )
    # A conditional database update protects the last slot against competing saves.
    return MonthlyUsage.objects.filter(pk=usage.pk, quotations__lt=plan["quotations"]).update(quotations=F("quotations") + 1) == 1


def reserved_seats(account):
    invitations = TeamInvitation.objects.filter(
        account=account, accepted_at__isnull=True, revoked_at__isnull=True, expires_at__gt=timezone.now(),
    ).count()
    return 1 + account.memberships.count() + invitations


def user_has_seat(user, account):
    if not account or account.owner_id == user.pk:
        return True
    seats = current_plan(account)["seats"]
    # After expiry, retain records and membership but restrict excess users to reading.
    return user.pk in account.memberships.order_by("created_at", "pk").values_list("user_id", flat=True)[:seats - 1]


def apply_billing_event(payload):
    """Apply a trusted sandbox event once, without storing its raw body."""
    if not (settings.DEBUG and settings.BILLING_SANDBOX_ENABLED) or not isinstance(payload, dict):
        raise ValidationError("Invalid event.")
    event_id, purchase_id, outcome = (payload.get(key) for key in ("id", "purchase_id", "outcome"))
    if not isinstance(event_id, str) or not 1 <= len(event_id) <= 100 or not isinstance(outcome, str) or outcome not in {"paid", "failed", "refunded"}:
        raise ValidationError("Invalid event.")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    try:
        purchase = SubscriptionPeriod.objects.get(pk=purchase_id, is_test=True)
    except (SubscriptionPeriod.DoesNotExist, ValueError, TypeError):
        raise ValidationError("Invalid purchase.")
    with transaction.atomic():
        # All entitlements, seat allocation and quotation saves share this lock.
        BusinessAccount.objects.select_for_update().get(pk=purchase.account_id)
        purchase = SubscriptionPeriod.objects.select_for_update().get(pk=purchase.pk)
        event, created = BillingEvent.objects.get_or_create(
            event_id=event_id, defaults={"purchase": purchase, "outcome": outcome, "payload_digest": digest},
        )
        if not created:
            if event.payload_digest != digest:
                raise ValidationError("Conflicting event identifier.")
            return purchase
        if purchase.status in {SubscriptionPeriod.Status.REFUNDED, SubscriptionPeriod.Status.CANCELLED}:
            return purchase
        if outcome == "paid" and purchase.status != SubscriptionPeriod.Status.PAID:
            now = timezone.now()
            # Renewals and tier changes start after prepaid access; no hidden proration.
            latest = paid_periods(purchase.account).filter(ends_at__gt=now).order_by("-ends_at").first()
            start = latest.ends_at if latest else now
            local_start = timezone.localtime(start)
            month_index = local_start.year * 12 + local_start.month - 1 + purchase.months
            year, month = divmod(month_index, 12)
            end = local_start.replace(year=year, month=month + 1, day=min(local_start.day, calendar.monthrange(year, month + 1)[1]))
            purchase.starts_at, purchase.ends_at = start, end
            purchase.status = SubscriptionPeriod.Status.PAID
        elif outcome == "refunded":
            # Refund-before-confirmation is terminal: a delayed success cannot regrant access.
            purchase.status = SubscriptionPeriod.Status.REFUNDED
        elif outcome == "failed" and purchase.status != SubscriptionPeriod.Status.PAID:
            purchase.status = SubscriptionPeriod.Status.FAILED
        purchase.save(update_fields=["status", "starts_at", "ends_at"])
        return purchase
