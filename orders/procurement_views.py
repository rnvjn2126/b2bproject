import uuid
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Exists, F, OuterRef, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .documents import purchase_order_pdf
from .forms import CancellationForm, MovementForm, PurchaseForm
from .models import PurchaseOrder, SalesOrder, SalesOrderLine
from .services import change_purchase_status, create_purchase, record_movement, total_quantity
from .views import order_manager


def purchase_queryset(workspace):
    return PurchaseOrder.objects.filter(requirement__order__workspace=workspace).select_related(
        "requirement__order__workspace",
    )


@order_manager
@require_http_methods(["GET", "POST"])
def purchase_create(request, workspace, pk):
    line = get_object_or_404(SalesOrderLine.objects.select_related("order__workspace", "quote_line"),
                             pk=pk, order__workspace=workspace)
    form = PurchaseForm(request.POST if request.method == "POST" else None, line=line, initial={
        "submission_key": uuid.uuid4(), "delivery_on": line.order.delivery_on,
    })
    if request.method == "POST" and form.is_valid():
        values = form.cleaned_data.copy()
        try:
            purchase = create_purchase(workspace, request.user, pk, values.pop("offer").pk, **values)
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            return redirect("orders:purchase_detail", pk=purchase.pk)
    return render(request, "orders/operation.html", {
        "title": "Prepare purchase order", "form": form, "submit": "Save purchase order",
        "note": f"Enter the allocation in {line.unit}, the sales requirement unit.",
    })


@order_manager
@require_GET
def purchase_detail(request, workspace, pk):
    purchase = get_object_or_404(purchase_queryset(workspace), pk=pk)
    return render(request, "orders/purchase.html", {
        "purchase": purchase, "cancellation_form": CancellationForm(), "received": total_quantity(purchase.receipts),
    })


@order_manager
@require_POST
def purchase_status(request, workspace, pk, target):
    purchase = get_object_or_404(purchase_queryset(workspace), pk=pk)
    reason = ""
    if target == SalesOrder.Status.CANCELLED:
        form = CancellationForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Enter a cancellation reason of up to 500 characters.")
            return redirect("orders:purchase_detail", pk=pk)
        reason = form.cleaned_data["reason"]
    try:
        change_purchase_status(workspace, request.user, purchase.pk, target, reason)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return redirect("orders:purchase_detail", pk=pk)


@order_manager
@require_GET
def purchase_pdf(request, workspace, pk):
    purchase = get_object_or_404(purchase_queryset(workspace), pk=pk, status=SalesOrder.Status.APPROVED)
    response = HttpResponse(purchase_order_pdf(purchase), content_type="application/pdf")
    response.headers["Content-Disposition"] = f'attachment; filename="{purchase.number}.pdf"'
    return response


@order_manager
@require_http_methods(["GET", "POST"])
def movement(request, workspace, pk, receipt):
    if receipt:
        source = get_object_or_404(purchase_queryset(workspace), pk=pk)
        back = ("orders:purchase_detail", source.pk)
        unit = source.requirement.unit
    else:
        source = get_object_or_404(SalesOrderLine, pk=pk, order__workspace=workspace)
        back = ("orders:sales_detail", source.order_id)
        unit = source.unit
    form = MovementForm(request.POST if request.method == "POST" else None, initial={"date": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        try:
            record_movement(workspace, request.user, source_id=pk, receipt=receipt, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            messages.success(request, "Goods movement recorded.")
            return redirect(back[0], pk=back[1])
    return render(request, "orders/operation.html", {
        "title": "Record goods receipt" if receipt else "Record dispatch",
        "form": form, "submit": "Record movement", "note": f"Enter the confirmed movement in {unit}.",
    })


@order_manager
@require_GET
def pending(request, workspace):
    open_lines = SalesOrderLine.objects.filter(order=OuterRef("pk")).annotate(
        sent=Coalesce(Sum("dispatches__quantity"), Decimal(0)),
    ).filter(quantity__gt=F("sent"))
    sales = SalesOrder.objects.filter(workspace=workspace).exclude(status=SalesOrder.Status.CANCELLED).filter(
        Exists(open_lines),
    ).order_by("delivery_on", "pk")
    purchases = purchase_queryset(workspace).exclude(status=SalesOrder.Status.CANCELLED).annotate(
        received=Coalesce(Sum("receipts__quantity"), Decimal(0)),
    ).filter(quantity__gt=F("received")).order_by("delivery_on", "pk")
    return render(request, "orders/pending.html", {
        "sales": Paginator(sales, 25).get_page(request.GET.get("sales_page")),
        "purchases": Paginator(purchases, 25).get_page(request.GET.get("purchase_page")),
    })
