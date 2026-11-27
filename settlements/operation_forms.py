from decimal import Decimal
from uuid import uuid4

from django import forms

from accounting.models import AccountGroup, Ledger
from accounting.services import CASH_LEDGER_CODES
from dashboard.models import Customer, Supplier
from invoicing.models import IssuedInvoice


DATE_INPUT = {"type": "date"}


class PartyForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False)
    supplier = forms.ModelChoiceField(queryset=Supplier.objects.none(), required=False)

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.filter(owner_id=workspace.owner_id)
        self.fields["supplier"].queryset = Supplier.objects.filter(owner_id=workspace.owner_id)

    def clean(self):
        cleaned = super().clean()
        if not self.errors and bool(cleaned.get("customer")) == bool(cleaned.get("supplier")):
            raise forms.ValidationError("Choose either a customer or a supplier.")
        return cleaned


class PaymentForm(PartyForm):
    posting_on = forms.DateField(widget=forms.DateInput(attrs=DATE_INPUT))
    amount = forms.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal("0.01"))
    funds_ledger = forms.ModelChoiceField(queryset=Ledger.objects.none(), label="Bank or cash ledger")
    control_ledger = forms.ModelChoiceField(queryset=Ledger.objects.none(), label="Party control ledger")
    external_reference = forms.CharField(max_length=100, required=False)
    narration = forms.CharField(max_length=500, required=False)
    submission_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid4)

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, workspace=workspace, **kwargs)
        same_company = Ledger.objects.filter(workspace=workspace, group__workspace=workspace)
        self.fields["funds_ledger"].queryset = same_company.filter(
            code__in=CASH_LEDGER_CODES, group__kind=AccountGroup.Kind.ASSET,
        )
        self.fields["control_ledger"].queryset = same_company.filter(
            group__kind__in=(AccountGroup.Kind.ASSET, AccountGroup.Kind.LIABILITY),
        ).exclude(code__in=CASH_LEDGER_CODES)


class AllocationForm(forms.Form):
    invoice = forms.ModelChoiceField(queryset=IssuedInvoice.objects.none())
    posted_on = forms.DateField(widget=forms.DateInput(attrs=DATE_INPUT))
    amount = forms.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal("0.01"))
    reason = forms.CharField(max_length=250, required=False)
    submission_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid4)

    def __init__(self, *args, workspace, payment, release=False, **kwargs):
        super().__init__(*args, **kwargs)
        if release:
            self.fields.pop("invoice")
            self.fields["reason"].required = True
        else:
            party = (
                {"draft__movement__sales_line__order__customer_id": payment.customer_id}
                if payment.customer_id else
                {"draft__movement__purchase_order__supplier_id": payment.supplier_id}
            )
            self.fields["invoice"].queryset = IssuedInvoice.objects.filter(
                workspace=workspace, journal__sealed=True, **party,
            ).order_by("-posting_on", "-pk")


class CreditProfileForm(PartyForm):
    credit_days = forms.IntegerField(min_value=0, max_value=365)
    credit_limit = forms.DecimalField(max_digits=15, decimal_places=2, min_value=0, required=False)


class InvoiceDueForm(forms.Form):
    due_on = forms.DateField(required=False, widget=forms.DateInput(attrs=DATE_INPUT))
    use_default = forms.BooleanField(required=False, label="Apply the party's credit terms")

    def clean(self):
        cleaned = super().clean()
        if not self.errors and bool(cleaned.get("due_on")) == bool(cleaned.get("use_default")):
            raise forms.ValidationError("Enter a due date or apply the party's credit terms.")
        return cleaned


class MseReviewForm(forms.Form):
    accepted_on = forms.DateField(widget=forms.DateInput(attrs=DATE_INPUT), label="Confirmed acceptance date")
    written_due_on = forms.DateField(widget=forms.DateInput(attrs=DATE_INPUT), required=False, label="Written due date")
    evidence_reference = forms.CharField(max_length=200)
    eligibility_reviewed = forms.BooleanField(label="Eligibility has been reviewed and confirmed")
