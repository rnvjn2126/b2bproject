from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from accounting.views import owner_only

from .models import FundsAccount
from .reconciliation import confirm_match, get_statement_entry, suggest_matches, unmatched_report
from .services import company_funds


class ReportFilter(forms.Form):
    account = forms.ModelChoiceField(queryset=FundsAccount.objects.none())
    start_on = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_on = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = company_funds(workspace).filter(kind=FundsAccount.Kind.BANK)


class MatchForm(forms.Form):
    journal_line_id = forms.TypedChoiceField(label="Candidate ledger entry", coerce=int)

    def __init__(self, *args, candidates, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["journal_line_id"].choices = [
            (line.pk, f"{line.journal.date} · {line.journal.transaction_reference} · "
                      f"INR {line.amount:.2f} · {line.journal.reference}") for line in candidates
        ]


@owner_only
@never_cache
@require_http_methods(["GET"])
def reconciliation_report(request, workspace):
    if workspace is None or not settings.INTERNAL_INVOICE_ISSUANCE:
        raise Http404
    today = timezone.localdate()
    form = ReportFilter(request.GET or None, workspace=workspace,
                        initial={"start_on": today.replace(day=1), "end_on": today})
    report = None
    if form.is_bound and form.is_valid():
        data = form.cleaned_data
        try:
            report = unmatched_report(workspace, request.user, account_id=data["account"].pk,
                                      start_on=data["start_on"], end_on=data["end_on"])
        except ValidationError as error:
            form.add_error(None, error.messages)
    return render(request, "banking/reconciliation.html", {"form": form, "report": report})


@owner_only
@never_cache
@require_http_methods(["GET", "POST"])
def reconciliation_confirm(request, workspace, pk):
    if workspace is None or not settings.INTERNAL_INVOICE_ISSUANCE:
        raise Http404
    try:
        entry = get_statement_entry(workspace, pk)
        candidates = suggest_matches(workspace, request.user, statement_line_id=pk)
    except ValidationError as error:
        raise Http404 from error
    form = MatchForm(request.POST if request.method == "POST" else None, candidates=candidates)
    if request.method == "POST" and form.is_valid():
        try:
            match = confirm_match(workspace, request.user, statement_line_id=pk, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            entry = match.statement_line
            return redirect(reverse("accounting:bank_reconciliation", query={
                "account": entry.account_id, "start_on": entry.posted_on.replace(day=1), "end_on": timezone.localdate(),
            }))
    return render(request, "banking/confirm.html", {"form": form, "candidates": candidates, "entry": entry})
