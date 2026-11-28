from datetime import date

from django.core.paginator import Paginator
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from invoicing.models import InvoiceDraft

from .models import Branch, Ledger
from .report_exports import CONTENT_TYPES, ROW_LIMITS, render_report
from .report_tables import REPORT_NAMES, report_table
from .report_forms import FinancialReportForm
from .reporting import ZERO, comparison_dates, financial_overview
from .statements import financial_statements
from .trade_reports import profitability, trade_register
from .views import financial_year_start, owner_only


def _dates(request, workspace, *, allow_comparison=False):
    today = timezone.localdate()
    defaults = {"start": date(financial_year_start(today), 4, 1), "end": today}
    data = request.GET.copy()
    if not any(data.get(key) for key in ("year", "start", "end")):
        data.update(defaults)
    form = FinancialReportForm(data, workspace=workspace)
    if not allow_comparison:
        del form.fields["comparison"]
    return form


@owner_only
@never_cache
@require_GET
def dashboard(request, workspace):
    form = _dates(request, workspace, allow_comparison=True)
    result = comparison = None
    if workspace and form.is_valid():
        data = form.cleaned_data
        start, end = data["start"], data["end"]
        result = financial_overview(workspace, request.user, start, end)
        other_dates = comparison_dates(start, end, data["comparison"])
        if other_dates:
            comparison = financial_overview(workspace, request.user, *other_dates)
    return render(request, "accounting/finance_dashboard.html", {
        "form": form, "report": result, "comparison": comparison, "workspace": workspace,
    })


@owner_only
@never_cache
@require_GET
def register(request, workspace, kind):
    if kind not in InvoiceDraft.Kind.values:
        raise Http404
    form = _dates(request, workspace)
    entries = None
    totals = None
    if workspace and form.is_valid():
        rows = trade_register(workspace, kind, form.cleaned_data["start"], form.cleaned_data["end"])
        entries = Paginator(rows, 50).get_page(request.GET.get("page"))
        totals = {key: sum((getattr(row, key) for row in rows), ZERO)
                  for key in ("trade_amount", "tax_posted", "invoice_amount")}
    return render(request, "accounting/trade_register.html", {"kind": kind, "form": form, "entries": entries, "totals": totals,
        "export_name": "sales" if kind == InvoiceDraft.Kind.SALES else "purchases",})


@owner_only
@never_cache
@require_GET
def finance_analysis(request, workspace):
    form = _dates(request, workspace)
    result = None
    if workspace and form.is_valid():
        start, end = form.cleaned_data["start"], form.cleaned_data["end"]
        sales = trade_register(workspace, InvoiceDraft.Kind.SALES, start, end)
        result = {
            "expenses": financial_statements(workspace, start, end)["profit_loss"][1],
            "customer": profitability(sales, "customer"),
            "product": profitability(sales, "product"),
        }
    return render(request, "accounting/finance_analysis.html", {"form": form, "result": result})


@owner_only
@never_cache
@require_GET
def export(request, workspace, report_name, format_name):
    if workspace is None or report_name not in REPORT_NAMES or format_name not in CONTENT_TYPES:
        raise Http404
    form = _dates(request, workspace)
    if not form.is_valid():
        return HttpResponseBadRequest("Choose a valid report date range or financial year.")
    ledger = branch = None
    if report_name == "ledger" and request.GET.get("ledger"):
        try:
            ledger_id = int(request.GET["ledger"])
        except (ValueError, OverflowError):
            raise Http404
        if not 0 < ledger_id <= 2**63 - 1:
            raise Http404
        ledger = get_object_or_404(Ledger, pk=ledger_id, workspace=workspace, group__workspace=workspace)
    if report_name in ("balance-sheet", "profit-loss", "trial-balance", "ledger", "day-book") and request.GET.get("branch"):
        try:
            branch_id = int(request.GET["branch"])
        except (ValueError, OverflowError):
            raise Http404
        if not 0 < branch_id <= 2**63 - 1:
            raise Http404
        branch = get_object_or_404(Branch, pk=branch_id, workspace=workspace)
    start, end = form.cleaned_data["start"], form.cleaned_data["end"]
    data = report_table(workspace, request.user, report_name, start, end, ledger=ledger, branch=branch)
    if len(data.rows) > ROW_LIMITS[format_name]:
        return HttpResponseBadRequest("Choose a narrower date range for this format.")
    response = HttpResponse(render_report(data, start, end, format_name), content_type=CONTENT_TYPES[format_name])
    response["Content-Disposition"] = content_disposition_header(True, f"{report_name}-{start}-{end}.{format_name}")
    return response
