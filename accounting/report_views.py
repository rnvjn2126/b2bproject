from datetime import date

from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .report_forms import FinancialReportForm
from .reporting import comparison_dates, financial_overview
from .views import financial_year_start, owner_only


@owner_only
@never_cache
@require_GET
def dashboard(request, workspace):
    today = timezone.localdate()
    defaults = {"start": date(financial_year_start(today), 4, 1), "end": today}
    form = FinancialReportForm(request.GET or defaults, workspace=workspace)
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
