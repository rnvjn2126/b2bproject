from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.utils import timezone
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from accounting.services import lock_books
from accounting.views import owner_only
from dashboard.accounts import business_account_for

from .forms import (
    InvoiceCancelForm, InvoiceDraftForm, InvoiceIssueForm, InvoiceReturnForm, RegistrationBrandingForm,
    RegistrationForm, TaxRateForm,
)
from .issuance import cancel_internal_invoice, issue_internal_purchase, issue_internal_sale
from .models import CompanyGSTRegistration, InvoiceDraft, IssuedInvoice, TaxRate
from .returns import record_invoice_return
from .services import eligible_movements, prepare_draft
from .words import rupees_in_words


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
def invoice_prepare(request, workspace, pk, replace_estimate=False):
    movement = get_object_or_404(eligible_movements(workspace), pk=pk)
    existing = InvoiceDraft.objects.filter(workspace=workspace, movement=movement).first()
    if replace_estimate and (not existing or existing.kind != InvoiceDraft.Kind.PURCHASE
                             or existing.snapshot.get("supplier_invoice_date")):
        raise Http404
    if existing and not replace_estimate:
        return redirect("accounting:invoice_draft", pk=existing.pk)
    form = InvoiceDraftForm(request.POST if request.method == "POST" else None, workspace=workspace,
                            purchase=movement.purchase_order_id is not None)
    if request.method == "POST" and form.is_valid():
        try:
            draft = prepare_draft(workspace, request.user, movement_id=movement.pk, replace_estimate=replace_estimate,
                                  **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            return redirect("accounting:invoice_draft", pk=draft.pk)
    return render(request, "invoicing/prepare.html", {"movement": movement, "form": form, "replace_estimate": replace_estimate})


@owner_only
@never_cache
@require_GET
def invoice_draft(request, workspace, pk):
    draft = get_object_or_404(InvoiceDraft, workspace=workspace, pk=pk)
    issued = IssuedInvoice.objects.filter(draft=draft, workspace=workspace).first() if settings.INTERNAL_INVOICE_ISSUANCE else None
    return render(request, "invoicing/draft.html", {
        "draft": draft, "snapshot": draft.snapshot, "issued": issued,
        "issue_enabled": settings.INTERNAL_INVOICE_ISSUANCE,
    })


@owner_only
@never_cache
@require_http_methods(["GET", "POST"])
def registration_branding(request, workspace, pk):
    registration = get_object_or_404(CompanyGSTRegistration, workspace=workspace, pk=pk)
    if request.method == "POST":
        form = RegistrationBrandingForm(request.POST, request.FILES)
        if form.is_valid():
            fields = {"letterhead": form.cleaned_data["letterhead"]}
            if form.cleaned_data["logo"]:
                fields["logo_png"] = form.cleaned_data["logo"]
            elif form.cleaned_data["remove_logo"]:
                fields["logo_png"] = b""
            with transaction.atomic():
                lock_books(workspace, request.user)
                CompanyGSTRegistration.objects.filter(workspace=workspace, pk=pk).update(**fields)
            return redirect("accounting:gst_settings")
    else:
        form = RegistrationBrandingForm(initial={"letterhead": registration.letterhead})
    return render(request, "invoicing/branding.html", {"registration": registration, "form": form})


@owner_only
@never_cache
@require_GET
def invoice_print(request, workspace, pk):
    if not settings.INTERNAL_INVOICE_ISSUANCE:
        raise Http404
    invoice = get_object_or_404(IssuedInvoice.objects.select_related("draft", "cancellation"), workspace=workspace, pk=pk)
    return render(request, "invoicing/print.html", {
        "invoice": invoice, "snapshot": invoice.snapshot, "amount_words": rupees_in_words(invoice.total),
        "returned": invoice.returns.exists(),
    })


@owner_only
@never_cache
@require_http_methods(["GET", "POST"])
def invoice_issue(request, workspace, pk):
    if not settings.INTERNAL_INVOICE_ISSUANCE:
        raise Http404
    draft = get_object_or_404(InvoiceDraft, workspace=workspace, pk=pk)
    previous = IssuedInvoice.objects.filter(workspace=workspace, draft=draft).first()
    if previous and request.method == "GET":
        return redirect("accounting:invoice_print", pk=previous.pk)

    form = None
    purchase = draft.kind == InvoiceDraft.Kind.PURCHASE
    blocked = None
    supplier_date = draft.snapshot.get("supplier_invoice_date")
    if purchase and not supplier_date:
        blocked = "This draft needs the actual supplier invoice price and date before it can be posted."
    else:
        try:
            form = InvoiceIssueForm(request.POST if request.method == "POST" else None,
                                    workspace=workspace, draft=draft, initial={"posting_on": draft.supply_on})
        except ValidationError as error:
            blocked = " ".join(error.messages)
    if form is not None and request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        inputs = {"draft_id": draft.pk, **{key: data[key] for key in ("posting_on", "confirmed_total", "ledger_ids")}}
        try:
            if purchase:
                invoice = issue_internal_purchase(
                    workspace, request.user, **inputs, supplier_invoice_date=date.fromisoformat(supplier_date),
                    supplier_reference=data["supplier_reference"], recoverable_input_tax=data["recoverable_input_tax"],
                )
            else:
                invoice = issue_internal_sale(workspace, request.user, **inputs)
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            return redirect("accounting:invoice_print", pk=invoice.pk)
    return render(request, "invoicing/action.html", {
        "draft": draft, "form": form, "blocked": blocked, "title": "Review internal invoice",
        "submit": "Confirm and post", "total": draft.total,
    })


@owner_only
@never_cache
@require_http_methods(["GET", "POST"])
def invoice_adjust(request, workspace, pk, action):
    if not settings.INTERNAL_INVOICE_ISSUANCE:
        raise Http404
    invoice = get_object_or_404(IssuedInvoice, workspace=workspace, pk=pk)
    cancelling = action == "cancel"
    form_class = InvoiceCancelForm if cancelling else InvoiceReturnForm
    form = form_class(request.POST if request.method == "POST" else None,
                      initial={"posting_on": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        service = cancel_internal_invoice if cancelling else record_invoice_return
        try:
            service(workspace, request.user, invoice_id=invoice.pk, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            return redirect("accounting:invoice_print", pk=invoice.pk)
    title = "Cancel internal invoice" if cancelling else "Record financial return"
    return render(request, "invoicing/action.html", {
        "invoice": invoice, "form": form, "title": title, "submit": title, "total": invoice.total,
    })
