from datetime import timedelta
from django.utils import timezone
from .accounts import business_account_for
from .models import SubscriptionPeriod


def grant_test_plan(user, tier="small"):
    """Provision synthetic entitlements only inside test databases."""
    account = business_account_for(user, create=True)
    return SubscriptionPeriod.objects.create(
        account=account, tier=tier, months=1, status="paid", is_test=False,
        starts_at=timezone.now() - timedelta(days=1), ends_at=timezone.now() + timedelta(days=30),
    )
