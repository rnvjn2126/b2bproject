from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from dashboard.accounts import business_account_for, can_manage_account
from dashboard.models import Quote

from .documents import sales_order_pdf
from .forms import CancellationForm, ConvertQuoteForm
from .models import SalesOrder
from .services import change_sales_status, convert_quote


def order_manager(view):
    @login_required
    @wraps(view)
    def scoped(request, *args, **kwargs):
        workspace = business_account_for(request.user)
        if not can_manage_account(request.user, workspace):
            raise PermissionDenied
        return view(request, workspace, *args, **kwargs)
    return scoped


@order_manager
@require_GET
def sales_orders(request, workspace):
    orders = SalesOrder.objects.filter(workspace=workspace)
    status = request.GET.get("status")
    if status in SalesOrder.Status.values:
        orders = orders.filter(status=status)
    return render(request, "orders/list.html", {
        "page": Paginator(orders, 25).get_page(request.GET.get("page")),
        "statuses": SalesOrder.Status.choices, "status": status,
    })


@order_manager
@require_http_methods(["GET", "POST"])
def convert(request, workspace, pk):
    owner_id = workspace.owner_id if workspace else request.user.pk
    quote = get_object_or_404(Quote, pk=pk, owner_id=owner_id, rfq__owner_id=owner_id, rfq__customer__owner_id=owner_id)
    form = ConvertQuoteForm(request.POST if request.method == "POST" else None, initial={"delivery_on": quote.rfq.required_by})
    if request.method == "POST" and form.is_valid():
        if workspace is None:
            workspace = business_account_for(request.user, create=True)
        try:
            order = convert_quote(workspace, request.user, quote.pk, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            return redirect("orders:sales_detail", pk=order.pk)
    return render(request, "orders/convert.html", {"quote": quote, "form": form})


@order_manager
@require_GET
def sales_detail(request, workspace, pk):
    order = get_object_or_404(SalesOrder.objects.prefetch_related("lines__purchases", "lines__dispatches"),
                              workspace=workspace, pk=pk)
    return render(request, "orders/detail.html", {"order": order, "cancellation_form": CancellationForm()})


@order_manager
@require_POST
def sales_status(request, workspace, pk, target):
    order = get_object_or_404(SalesOrder, workspace=workspace, pk=pk)
    reason = ""
    if target == SalesOrder.Status.CANCELLED:
        form = CancellationForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Enter a cancellation reason of up to 500 characters.")
            return redirect("orders:sales_detail", pk=pk)
        reason = form.cleaned_data["reason"]
    try:
        change_sales_status(workspace, request.user, order.pk, target, reason)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return redirect("orders:sales_detail", pk=pk)


@order_manager
@require_GET
def sales_pdf(request, workspace, pk):
    order = get_object_or_404(SalesOrder.objects.select_related("workspace").prefetch_related("lines"),
                              workspace=workspace, pk=pk, status=SalesOrder.Status.APPROVED)
    response = HttpResponse(sales_order_pdf(order), content_type="application/pdf")
    response.headers["Content-Disposition"] = f'attachment; filename="{order.number}.pdf"'
    return response
