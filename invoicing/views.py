from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from accounting.services import lock_books
from accounting.views import owner_only
from dashboard.accounts import business_account_for

from .forms import RegistrationForm, TaxRateForm
from .models import CompanyGSTRegistration, TaxRate


@owner_only
@never_cache
@require_http_methods(["GET", "POST"])
def gst_settings(request, workspace):
    action = request.POST.get("action")
    forms = {
        "registration": RegistrationForm(request.POST if action == "registration" else None, prefix="registration"),
        "rate": TaxRateForm(request.POST if action == "rate" else None, prefix="rate"),
    }
    form = forms.get(action)
    if form is not None and form.is_valid():
        workspace = workspace or business_account_for(request.user, create=True)
        with transaction.atomic():
            lock_books(workspace, request.user)
            record = form.save(commit=False)
            record.workspace = workspace
            if isinstance(record, CompanyGSTRegistration):
                duplicate = CompanyGSTRegistration.objects.filter(workspace=workspace, gstin=record.gstin).exists()
            else:
                duplicate = TaxRate.objects.filter(
                    workspace=workspace, item_kind=record.item_kind, item_code=record.item_code,
                    effective_from=record.effective_from,
                ).exists()
            if duplicate:
                form.add_error(None, "This registration or rate version is already recorded for your company.")
            else:
                record.save()
                return redirect("accounting:gst_settings")
    return render(request, "invoicing/settings.html", {
        "registration_form": forms["registration"], "rate_form": forms["rate"],
        "registrations": CompanyGSTRegistration.objects.filter(workspace=workspace).order_by("gstin"),
        "rates": TaxRate.objects.filter(workspace=workspace).order_by("-effective_from", "item_code")[:50],
    })
