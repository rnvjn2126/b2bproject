from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Prefetch
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from accounting.views import owner_only

from . import forms
from .counts import record_physical_count
from .cutting import CutOutput, record_stock_cut
from .models import LotCertificate, SteelSpecification, StockCount, StockCut, StockCutOutput, StockLot, StockMovement, StockReservation, ValuationPolicy, Warehouse
from .purchase_costs import capitalise_purchase_cost
from .reconciliation import reconcile_stock_to_ledger
from .reports import reorder_status, set_reorder_policy, stock_ageing
from .reservations import record_reservation_action, reserve_stock
from .sale_costs import post_sale_cost
from .services import save_specification
from .stock import record_stock_movement
from .stock_setup import MAX_CERTIFICATE_BYTES, attach_lot_certificate, register_location, register_lot, register_warehouse
from .supplier_rates import company_daily_rates, latest_daily_rates, recommend_procurement, record_daily_rate
from .valuation import set_valuation_method, value_stock_movement


ACTIONS = {
    "specification": ("Save steel specification", forms.SpecificationForm, save_specification),
    "warehouse": ("Register warehouse", forms.WarehouseForm, register_warehouse),
    "location": ("Register storage location", forms.LocationForm, register_location),
    "lot": ("Register steel lot", forms.LotForm, register_lot),
    "movement": ("Record stock movement", forms.MovementForm, record_stock_movement),
    "reservation": ("Reserve stock", forms.ReservationForm, reserve_stock),
    "count": ("Record physical count", forms.CountForm, record_physical_count),
    "valuation-method": ("Set valuation method", forms.ValuationMethodForm, set_valuation_method),
    "value-movement": ("Value stock movement", forms.ValueMovementForm, value_stock_movement),
    "reorder": ("Save reorder threshold", forms.ReorderForm, set_reorder_policy),
}
STOCK_COST_ACTIONS = {
    "purchase-cost": ("Capitalise a purchase", forms.InvoiceStockCostForm, capitalise_purchase_cost),
    "sale-cost": ("Post the cost of a sale", forms.SaleStockCostForm, post_sale_cost),
}
FORM_HELP = {
    "value-movement": "Enter material cost for receipts. Leave material blank and other costs at zero for issues and transfers.",
    "specification": "Use the dimensions relevant to the selected profile. Existing lots retain their recorded specifications.",
    "movement": "Choose a destination for receipts, a source for issues, and both for transfers. Use the unit registered on the lot.",
    "count": "Enter the total physically counted in the lot’s unit. A difference records a stock adjustment.",
    "reorder": "Enter the minimum available quantity in the catalogue unit. Reserved stock is excluded.",
}


def _check_access(workspace):
    if workspace is None or not settings.INTERNAL_INVENTORY:
        raise Http404


def _lots(workspace):
    return StockLot.objects.filter(workspace=workspace, product__owner_id=workspace.owner_id)


def _reservations(workspace):
    return StockReservation.objects.filter(
        workspace=workspace, position__lot__in=_lots(workspace), position__location__warehouse__workspace=workspace,
    ).select_related("position__lot__product", "position__location__warehouse")


@owner_only
@never_cache
@require_GET
def overview(request, workspace):
    _check_access(workspace)
    lots = _lots(workspace)
    return render(request, "inventory/overview.html", {
        "actions": ACTIONS,
        "warehouses": Warehouse.objects.filter(workspace=workspace).prefetch_related("locations"),
        "specifications": SteelSpecification.objects.filter(
            workspace=workspace, product__owner_id=workspace.owner_id,
        ).select_related("product"),
        "lots": lots.select_related("product").annotate(
            has_certificate=Exists(LotCertificate.objects.filter(lot_id=OuterRef("pk"))),
        ),
        "ageing": stock_ageing(workspace),
        "reorders": reorder_status(workspace),
        "reservations": _reservations(workspace).filter(remaining__gt=0).order_by("-posted_on", "-pk"),
        "counts": StockCount.objects.filter(
            workspace=workspace, position__lot__in=lots, position__location__warehouse__workspace=workspace,
        ).select_related("position__lot__product", "position__location__warehouse").order_by("-posted_on", "-pk")[:20],
        "movements": StockMovement.objects.filter(workspace=workspace, lot__in=lots).select_related(
            "lot__product", "source__warehouse", "destination__warehouse", "physical_count",
        ).order_by("-posted_on", "-pk")[:30],
    })


def _save(request, workspace, title, form_class, save, *, description="", **identifiers):
    form = form_class(request.POST if request.method == "POST" else None, workspace=workspace,
                      initial={"posted_on": timezone.localdate()})
    if form.is_valid():
        try:
            save(workspace, request.user, **form.arguments(), **identifiers)
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            messages.success(request, "Inventory record saved.")
            return redirect("accounting:inventory:overview")
    return render(request, "inventory/form.html", {"form": form, "title": title, "description": description})


@owner_only
@never_cache
@require_http_methods(["GET", "POST"])
def action(request, workspace, kind):
    _check_access(workspace)
    actions = ACTIONS | STOCK_COST_ACTIONS if settings.INTERNAL_STOCK_ACCOUNTING else ACTIONS
    if kind not in actions:
        raise Http404
    return _save(request, workspace, *actions[kind], description=FORM_HELP.get(kind, ""))


@owner_only
@never_cache
@require_http_methods(["GET", "POST"])
def reservation_action(request, workspace, pk):
    _check_access(workspace)
    reservation = get_object_or_404(_reservations(workspace), pk=pk)
    return _save(request, workspace, "Release or issue reserved stock", forms.ReservationActionForm,
                 record_reservation_action, reservation_id=reservation.pk,
                 description=f"{reservation.position.lot} · {reservation.position.location} · "
                             f"{reservation.remaining:g} {reservation.position.lot.get_unit_display()} remaining")


@owner_only
@never_cache
@require_http_methods(["GET", "POST"])
def certificate_upload(request, workspace, pk):
    _check_access(workspace)
    lot = get_object_or_404(_lots(workspace).select_related("product"), pk=pk)
    form = forms.CertificateForm(request.POST, request.FILES) if request.method == "POST" else forms.CertificateForm()
    if form.is_valid():
        upload = form.cleaned_data["certificate"]
        try:
            if upload.size > MAX_CERTIFICATE_BYTES:
                raise ValidationError("Choose a PDF certificate up to 512 KB.")
            attach_lot_certificate(workspace, request.user, lot_id=lot.pk, content=upload.read(MAX_CERTIFICATE_BYTES + 1))
        except ValidationError as error:
            form.add_error("certificate", error.messages)
        else:
            messages.success(request, "Certificate attached.")
            return redirect("accounting:inventory:overview")
    return render(request, "inventory/form.html", {
        "form": form, "title": "Attach mill test certificate", "description": f"{lot} · PDF up to 512 KB", "upload": True,
    })


@owner_only
@never_cache
@require_GET
def certificate_download(request, workspace, pk):
    _check_access(workspace)
    certificate = get_object_or_404(LotCertificate.objects.select_related("lot"), lot_id=pk, lot__in=_lots(workspace))
    response = HttpResponse(bytes(certificate.content), content_type="application/octet-stream")
    response["Content-Disposition"] = content_disposition_header(True, f"{certificate.lot.code}-certificate.pdf")
    return response


@owner_only
@never_cache
@require_http_methods(["GET", "POST"])
def supplier_rate_board(request, workspace):
    _check_access(workspace)
    today = timezone.localdate()
    rate_form = forms.DailyRateForm(request.POST if request.method == "POST" else None, workspace=workspace,
                                    initial={"quoted_on": today, "valid_through": today})
    if rate_form.is_valid():
        try:
            record_daily_rate(workspace, request.user, **rate_form.arguments())
        except ValidationError as error:
            rate_form.add_error(None, error.messages)
        else:
            messages.success(request, "Supplier rate recorded.")
            return redirect("accounting:inventory:supplier_rates")

    plan_form = forms.ProcurementPlanForm(request.GET if "plan-product_id" in request.GET else None,
                                          workspace=workspace, prefix="plan")
    plan = None
    if plan_form.is_valid():
        try:
            plan = recommend_procurement(workspace, as_of=today, **plan_form.arguments())
        except ValidationError as error:
            plan_form.add_error(None, error.messages)
    return render(request, "inventory/supplier_rates.html", {
        "rate_form": rate_form, "plan_form": plan_form, "plan": plan, "today": today,
        "current_rates": Paginator(latest_daily_rates(workspace, today), 25).get_page(request.GET.get("current_page")),
        "history": Paginator(company_daily_rates(workspace), 25).get_page(request.GET.get("history_page")),
    })


@owner_only
@never_cache
@require_GET
def valuation_review(request, workspace):
    _check_access(workspace)
    today = timezone.localdate()
    form = forms.StockReconciliationForm(request.GET or None, workspace=workspace, initial={"as_of": today})
    result = None
    if form.is_valid():
        try:
            result = reconcile_stock_to_ledger(workspace, request.user, **form.arguments())
        except ValidationError as error:
            form.add_error(None, error.messages)
    return render(request, "inventory/valuation_review.html", {
        "form": form, "result": result, "policy": ValuationPolicy.objects.filter(workspace=workspace).first(),
        "stock_cost_actions": STOCK_COST_ACTIONS if settings.INTERNAL_STOCK_ACCOUNTING else {},
    })


@owner_only
@never_cache
@require_http_methods(["GET", "POST"])
def cut_stock(request, workspace):
    _check_access(workspace)
    data = request.POST if request.method == "POST" else None
    form = forms.CutStockForm(data, workspace=workspace, initial={"posted_on": timezone.localdate()})
    outputs = forms.CutOutputs(data, prefix="outputs", form_kwargs={"workspace": workspace})
    if form.is_valid() and outputs.is_valid():
        try:
            record_stock_cut(
                workspace, request.user, **form.arguments(),
                outputs=[CutOutput(**part.arguments()) for part in outputs if part.cleaned_data],
            )
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            messages.success(request, "Stock cut saved.")
            return redirect("accounting:inventory:cut_stock")
    cuts = StockCut.objects.filter(workspace=workspace, source__movement__workspace=workspace).select_related(
        "source__movement__lot__product",
    ).prefetch_related(Prefetch(
        "outputs", queryset=StockCutOutput.objects.filter(receipt__movement__workspace=workspace).select_related(
            "receipt__movement__lot__product",
        ),
    )).order_by("-source__movement__posted_on", "-pk")[:20]
    return render(request, "inventory/cut_stock.html", {"form": form, "outputs": outputs, "cuts": cuts})
