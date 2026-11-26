from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from accounting.services import lock_books
from accounting.views import owner_only
from dashboard.accounts import business_account_for

from .forms import InvoiceDraftForm, RegistrationForm, TaxRateForm
from .models import CompanyGSTRegistration, InvoiceDraft, TaxRate
from .services import eligible_movements, prepare_draft


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


@owner_only
@never_cache
@require_GET
def invoice_movements(request, workspace):
    movements = eligible_movements(workspace).order_by("-date", "-pk")
    page = Paginator(movements, 25).get_page(request.GET.get("page"))
    return render(request, "invoicing/movements.html", {"page": page})


@owner_only
@never_cache
@require_http_methods(["GET", "POST"])
def invoice_prepare(request, workspace, pk):
    movement = get_object_or_404(eligible_movements(workspace), pk=pk)
    existing = InvoiceDraft.objects.filter(workspace=workspace, movement=movement).first()
    if existing:
        return redirect("accounting:invoice_draft", pk=existing.pk)
    form = InvoiceDraftForm(request.POST if request.method == "POST" else None, workspace=workspace,
                            purchase=movement.purchase_order_id is not None)
    if request.method == "POST" and form.is_valid():
        try:
            draft = prepare_draft(workspace, request.user, movement_id=movement.pk, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            return redirect("accounting:invoice_draft", pk=draft.pk)
    return render(request, "invoicing/prepare.html", {"movement": movement, "form": form})


@owner_only
@never_cache
@require_GET
def invoice_draft(request, workspace, pk):
    draft = get_object_or_404(InvoiceDraft, workspace=workspace, pk=pk)
    return render(request, "invoicing/draft.html", {"draft": draft, "snapshot": draft.snapshot})
