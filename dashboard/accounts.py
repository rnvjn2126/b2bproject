from .models import (
    BusinessAccount, Customer, FollowUp, Product, Quote, QuoteLine, QuotePricingSettings,
    RFQ, RFQLine, Supplier, SupplierOffer, TeamMembership,
)


def business_account_for(user, *, create=False):
    membership = TeamMembership.objects.select_related("account").filter(user=user).first()
    if membership:
        return membership.account

    account = BusinessAccount.objects.filter(owner=user).first()
    if account or not create:
        return account
    return BusinessAccount.objects.get_or_create(owner=user, defaults={"name": user.get_username()})[0]


def account_owner(user):
    account = business_account_for(user)
    return account.owner if account else user


def can_manage_account(user, account=None):
    account = account or business_account_for(user)
    if not account or account.owner_id == user.pk:
        return True
    membership = TeamMembership.objects.filter(account=account, user=user).first()
    return membership is not None and membership.role == TeamMembership.Role.MANAGER


def can_manage_team(user, account):
    return account.owner_id == user.pk


def user_can_join_account(user):
    if TeamMembership.objects.filter(user=user).exists() or BusinessAccount.objects.filter(owner=user).exists():
        return False
    owned_models = (
        Customer, Supplier, Product, RFQ, RFQLine, FollowUp, SupplierOffer,
        Quote, QuoteLine, QuotePricingSettings,
    )
    return not any(model.objects.filter(owner=user).exists() for model in owned_models)
