from decimal import Decimal
from uuid import uuid4

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from accounting.models import Ledger
from accounting.views import owner_only

from .instruments import record_cheque_event, record_instrument
from .models import ChequeEvent, FundsAccount, ReportedInstrument
from .services import company_funds, funds_book, register_funds_account, transfer_funds


class AccountForm(forms.Form):
    ledger = forms.ModelChoiceField(queryset=Ledger.objects.none())
    name = forms.CharField(max_length=100)
    kind = forms.ChoiceField(choices=FundsAccount.Kind.choices)
    last_four = forms.RegexField(r"\A[0-9]{4}\Z", required=False, label="Last four bank account digits")

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ledger"].queryset = Ledger.objects.filter(
            workspace=workspace, group__workspace=workspace, group__kind="asset", funds_account__isnull=True,
        )


class TransferForm(forms.Form):
    posting_on = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    from_account = forms.ModelChoiceField(queryset=FundsAccount.objects.none(), label="From account")
    to_account = forms.ModelChoiceField(queryset=FundsAccount.objects.none(), label="To account")
    amount = forms.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal("0.01"))
    reference = forms.CharField(max_length=100, required=False)
    submission_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid4)

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        accounts = company_funds(workspace)
        self.fields["from_account"].queryset = accounts
        self.fields["to_account"].queryset = accounts


class BookDates(forms.Form):
    start_on = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_on = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))


class InstrumentForm(forms.Form):
    method = forms.ChoiceField(choices=ReportedInstrument.Method.choices)
    direction = forms.ChoiceField(choices=ReportedInstrument.Direction.choices)
    reference = forms.CharField(max_length=80)
    amount = forms.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal("0.01"))
    reported_on = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))


class ChequeEventForm(forms.Form):
    state = forms.ChoiceField(choices=ChequeEvent.State.choices)
    happened_on = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    reason = forms.CharField(max_length=250, required=False)
    submission_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid4)


def _require_bank_workspace(workspace):
    if workspace is None or not settings.INTERNAL_INVOICE_ISSUANCE:
        raise Http404


@owner_only
@never_cache
@require_http_methods(["GET", "POST"])
def accounts(request, workspace):
    _require_bank_workspace(workspace)
    form = AccountForm(request.POST if request.method == "POST" else None, workspace=workspace)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            account = register_funds_account(workspace, request.user, ledger_id=data["ledger"].pk,
                                             name=data["name"], kind=data["kind"], last_four=data["last_four"])
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            return redirect("accounting:bank_book", pk=account.pk)
    return render(request, "banking/accounts.html", {"form": form, "accounts": company_funds(workspace)})


@owner_only
@never_cache
@require_http_methods(["GET"])
def book(request, workspace, pk):
    _require_bank_workspace(workspace)
    account = get_object_or_404(company_funds(workspace), pk=pk)
    today = timezone.localdate()
    form = BookDates(request.GET or None, initial={"start_on": today.replace(day=1), "end_on": today})
    report = None
    if not form.is_bound or form.is_valid():
        date_range = form.cleaned_data if form.is_bound else form.initial
        try:
            report = funds_book(workspace, account_id=account.pk, **date_range)
        except ValidationError as error:
            form.add_error(None, error.messages)
    instruments = ReportedInstrument.objects.filter(account=account).order_by("-reported_on", "-pk")
    return render(request, "banking/book.html", {
        "account": account, "form": form, "report": report, "instruments": instruments,
    })


@owner_only
@never_cache
@require_http_methods(["GET", "POST"])
def transfer(request, workspace):
    _require_bank_workspace(workspace)
    form = TransferForm(request.POST if request.method == "POST" else None, workspace=workspace,
                        initial={"posting_on": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            journal = transfer_funds(workspace, request.user, from_id=data["from_account"].pk,
                                     to_id=data["to_account"].pk, posting_on=data["posting_on"], amount=data["amount"],
                                     submission_key=data["submission_key"], reference=data["reference"])
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            return redirect("accounting:journal", pk=journal.pk)
    return render(request, "banking/action.html", {"title": "Transfer funds", "form": form})


@owner_only
@never_cache
@require_http_methods(["GET", "POST"])
def instrument(request, workspace, pk):
    _require_bank_workspace(workspace)
    account = get_object_or_404(company_funds(workspace), pk=pk, kind=FundsAccount.Kind.BANK)
    form = InstrumentForm(request.POST if request.method == "POST" else None, initial={"reported_on": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        try:
            record_instrument(workspace, request.user, account_id=account.pk, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            return redirect("accounting:bank_book", pk=account.pk)
    return render(request, "banking/action.html", {
        "title": "Record payment reference", "form": form, "account": account,
        "note": "Staff-entered references stay separate from payment verification and journal posting.",
    })


@owner_only
@never_cache
@require_http_methods(["GET", "POST"])
def cheque(request, workspace, pk):
    _require_bank_workspace(workspace)
    entry = get_object_or_404(
        ReportedInstrument.objects.select_related("account"),
        pk=pk, account__in=company_funds(workspace), method=ReportedInstrument.Method.CHEQUE,
    )
    form = ChequeEventForm(request.POST if request.method == "POST" else None, initial={"happened_on": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        try:
            record_cheque_event(workspace, request.user, instrument_id=entry.pk, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            return redirect("accounting:bank_cheque", pk=entry.pk)
    return render(request, "banking/action.html", {
        "title": "Reported cheque history", "form": form, "account": entry.account, "cheque": entry,
        "note": "Reported cheque statuses stay separate from ledger balances.",
    })
