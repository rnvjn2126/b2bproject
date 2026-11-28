from datetime import date
from pathlib import PurePath

from django import forms
from django.conf import settings
from django.contrib import messages
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .models import TallyImportBatch
from .report_forms import FinancialReportForm
from .tally_exports import export_tally_vouchers
from .tally_imports import run_tally_import
from .tally_xml import MAX_BYTES
from .views import financial_year_start, owner_only


PREVIEW_SALT = "steel-quotes.tally-import-preview"


class TallyUploadForm(forms.Form):
    source = forms.FileField(label="Tally XML or prepared Excel workbook")
    opening_on = forms.DateField(label="Opening balance date", required=False,
                                 widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    mapping = forms.JSONField(label="Field mapping", required=False, widget=forms.Textarea(attrs={"rows": 4}),
                              help_text='Optional. Example: {"ledgers": {"Tally Cash": "1000"}}.')

    def clean_source(self):
        upload = self.cleaned_data["source"]
        kind = PurePath(upload.name).suffix.lower().lstrip(".")
        if kind not in ("xml", "xlsx") or upload.size > MAX_BYTES:
            raise ValidationError("Choose an XML or XLSX file up to 512 KiB.")
        return kind, upload.read(MAX_BYTES + 1)


class TallyConfirmForm(TallyUploadForm):
    opening_on = forms.DateField(required=False, widget=forms.HiddenInput)
    mapping = forms.JSONField(required=False, widget=forms.HiddenInput)
    preview_token = forms.CharField(widget=forms.HiddenInput)


def _enabled(workspace):
    if workspace is None or not settings.INTERNAL_TALLY_IMPORT:
        raise Http404


@owner_only
@never_cache
@require_http_methods(["GET", "POST"])
def migration(request, workspace):
    _enabled(workspace)
    form = TallyUploadForm()
    preview = confirmation = None
    if request.method == "POST":
        confirm = request.POST.get("action") == "confirm"
        active = (TallyConfirmForm if confirm else TallyUploadForm)(
            request.POST, request.FILES, prefix="confirm" if confirm else None,
        )
        if confirm:
            confirmation = active
        else:
            form = active
        if active.is_valid():
            data = active.cleaned_data
            source_format, content = data["source"]
            options = {"opening_on": data["opening_on"], "mapping": data["mapping"], "source_format": source_format}
            try:
                if confirm:
                    token = signing.loads(data["preview_token"], salt=PREVIEW_SALT, max_age=900)
                    if token[:2] != [workspace.pk, request.user.pk]:
                        raise signing.BadSignature
                    batch = run_tally_import(workspace, request.user, content, confirmed_key=token[2], **options)
                    messages.success(request, f"Import recorded. {batch.created_count} new and {batch.reused_count} reused records.")
                    return redirect("accounting:tally_migration")
                preview = run_tally_import(workspace, request.user, content, **options)
                if not preview.previously_committed:
                    confirmation = TallyConfirmForm(prefix="confirm", initial={
                        "opening_on": data["opening_on"], "mapping": data["mapping"],
                        "preview_token": signing.dumps([workspace.pk, request.user.pk, preview.key], salt=PREVIEW_SALT),
                    })
            except signing.BadSignature:
                active.add_error(None, "Run a new import preview for this workspace before confirming.")
            except ValidationError as error:
                active.add_error(None, error.messages)
    history = Paginator(TallyImportBatch.objects.filter(workspace=workspace), 25).get_page(request.GET.get("page"))
    today = timezone.localdate()
    export_dates = FinancialReportForm(workspace=workspace, initial={
        "start": date(financial_year_start(today), 4, 1), "end": today,
    })
    del export_dates.fields["comparison"]
    return render(request, "accounting/tally_migration.html", {
        "form": form, "preview": preview, "confirmation": confirmation, "history": history, "export_dates": export_dates,
    })


@owner_only
@never_cache
@require_GET
def download(request, workspace):
    _enabled(workspace)
    form = FinancialReportForm(request.GET, workspace=workspace)
    if not form.is_valid():
        return HttpResponseBadRequest("Choose dates or a financial year before exporting.")
    start, end = form.cleaned_data["start"], form.cleaned_data["end"]
    try:
        content = export_tally_vouchers(workspace, request.user, start, end)
    except ValidationError as error:
        return HttpResponseBadRequest(" ".join(error.messages), content_type="text/plain; charset=utf-8")
    response = HttpResponse(content, content_type="application/xml")
    response["Content-Disposition"] = content_disposition_header(True, f"tally-vouchers-{start}-{end}.xml")
    return response
