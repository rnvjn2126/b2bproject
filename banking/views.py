from django import forms
from django.conf import settings
from django.contrib import messages
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
from .statement_csv import MAX_STATEMENT_BYTES
from .statements import import_statement, preview_statement


class ReportFilter(forms.Form):
    account = forms.ModelChoiceField(queryset=FundsAccount.objects.none())
    start_on = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_on = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = company_funds(workspace).filter(kind=FundsAccount.Kind.BANK)


class MatchSearchForm(forms.Form):
    reference = forms.CharField(label="Search by exact journal or payment reference", required=False, max_length=100)


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
    search = MatchSearchForm(request.GET)
    try:
        entry = get_statement_entry(workspace, pk)
        candidates = (suggest_matches(workspace, request.user, statement_line_id=pk,
                                      reference=search.cleaned_data["reference"]) if search.is_valid() else [])
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
    return render(request, "banking/confirm.html", {"form": form, "search": search, "candidates": candidates, "entry": entry})



class StatementUploadForm(forms.Form):
    account = forms.ModelChoiceField(queryset=FundsAccount.objects.none())
    statement = forms.FileField(label="Statement file", widget=forms.ClearableFileInput(attrs={"accept": ".csv,.xlsx"}))

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = company_funds(workspace).filter(kind=FundsAccount.Kind.BANK)

    def clean_statement(self):
        upload = self.cleaned_data["statement"]
        file_format = upload.name.lower().rpartition(".")[2]
        if file_format not in ("csv", "xlsx") or upload.size > MAX_STATEMENT_BYTES:
            raise ValidationError("Choose a CSV or XLSX file up to 256 KB.")
        return file_format, upload.read(MAX_STATEMENT_BYTES + 1)


class StatementConfirmForm(StatementUploadForm):
    account = forms.ModelChoiceField(queryset=FundsAccount.objects.none(), widget=forms.HiddenInput)
    preview_digest = forms.RegexField(r"\A[0-9a-f]{64}\Z", widget=forms.HiddenInput)
    skip_known = forms.BooleanField(required=False, label="Skip entries already imported for this account")


@owner_only
@never_cache
@require_http_methods(["GET", "POST"])
def statement_upload(request, workspace):
    if workspace is None or not settings.INTERNAL_INVOICE_ISSUANCE:
        raise Http404
    form = StatementUploadForm(workspace=workspace)
    confirmation = None
    preview = None
    if request.method == "POST":
        confirming = request.POST.get("action") == "confirm"
        form_class = StatementConfirmForm if confirming else StatementUploadForm
        bound = form_class(request.POST, request.FILES, workspace=workspace, prefix="confirm" if confirming else None)
        if confirming:
            confirmation = bound
        else:
            form = bound
        if bound.is_valid():
            data = bound.cleaned_data
            account = data["account"]
            file_format, content = data["statement"]
            inputs = {"account_id": account.pk, "content": content, "file_format": file_format}
            try:
                if confirming:
                    batch = import_statement(workspace, request.user, **inputs, preview_digest=data["preview_digest"],
                                             skip_known=data["skip_known"])
                    messages.success(request, f"New entries staged: {batch.imported_rows}. "
                                              f"Entries already present: {batch.duplicate_rows}.")
                    today = timezone.localdate()
                    start = batch.lines.order_by("posted_on").values_list("posted_on", flat=True).first()
                    return redirect(reverse("accounting:bank_reconciliation", query={
                        "account": account.pk, "start_on": start or today.replace(day=1), "end_on": today,
                    }))
                preview = preview_statement(workspace, request.user, **inputs)
                confirmation = StatementConfirmForm(workspace=workspace, prefix="confirm", initial={
                    "account": account.pk, "preview_digest": preview.digest,
                })
            except ValidationError as error:
                bound.add_error(None, error.messages)
    return render(request, "banking/statement_upload.html", {
        "form": form, "confirmation": confirmation, "preview": preview,
    })
