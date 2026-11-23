from .accounts import business_account_for, can_manage_account
from .models import UserPreferences
from .billing import current_plan


def workspace_preferences(request):
    if not request.user.is_authenticated:
        return {}
    account = business_account_for(request.user)
    return {
        "display_preferences": UserPreferences.objects.filter(user=request.user).first(),
        "workspace_name": account.name if account else "Workspace",
        "workspace_plan": current_plan(account),
        "can_edit_company_defaults": can_manage_account(request.user, account),
    }
