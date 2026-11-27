from decimal import Decimal
from io import BytesIO
from uuid import uuid4

from django import forms
from PIL import Image

from accounting.models import Ledger

from .models import CompanyGSTRegistration, InvoiceDraft, TaxRate
from .posting import INVOICE_LEDGER_KINDS, plan_invoice_posting
from .tax import validate_gstin


class RegistrationForm(forms.ModelForm):
    class Meta:
        model = CompanyGSTRegistration
        fields = ("gstin", "registered_name", "registered_address")


class RegistrationBrandingForm(forms.Form):
    letterhead = forms.CharField(max_length=240, widget=forms.Textarea(attrs={"rows": 3}), required=False)
    logo = forms.FileField(required=False, help_text="PNG or JPEG, up to 256 KB and 1024 × 1024 pixels.")
    remove_logo = forms.BooleanField(required=False)

    def clean_logo(self):
        upload = self.cleaned_data["logo"]
        if not upload:
            return None
        if upload.size > 256 * 1024:
            raise forms.ValidationError("Choose a logo up to 256 KB.")
        try:
            with Image.open(upload, formats=("PNG", "JPEG")) as source:
                if max(source.size) > 1024:
                    raise forms.ValidationError("Choose a logo no larger than 1024 × 1024 pixels.")
                source.thumbnail((240, 240))
                logo = source.convert("RGBA")
                logo.info.clear()
                result = BytesIO()
                logo.save(result, format="PNG")
        except (OSError, ValueError, Image.DecompressionBombError):
            raise forms.ValidationError("Choose a valid PNG or JPEG logo.") from None
        return result.getvalue()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("logo") and cleaned.get("remove_logo"):
            self.add_error("logo", "Choose a new logo or remove the existing one.")
        return cleaned


class TaxRateForm(forms.ModelForm):
    class Meta:
        model = TaxRate
        fields = ("item_kind", "item_code", "effective_from", "source_url", "integrated_rate", "central_rate",
                  "local_rate", "cess_rate")
        widgets = {"effective_from": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def clean(self):
        cleaned = super().clean()
        for field in ("integrated_rate", "central_rate", "local_rate", "cess_rate"):
            if field in cleaned and not 0 <= cleaned[field] <= 100:
                self.add_error(field, "Enter a percentage between 0 and 100.")
        return cleaned


class InvoiceDraftForm(forms.Form):
    registration_id = forms.TypedChoiceField(label="Company registration", coerce=int)
    party_gstin = forms.CharField(label="Trading party GSTIN", max_length=15, validators=[validate_gstin])
    item_code = forms.RegexField(r"\A(?:[0-9]{4}|[0-9]{6}|[0-9]{8})\Z", label="HSN code", max_length=8)
    place_of_supply = forms.RegexField(r"\A[0-9]{2}\Z", label="Place of supply (two-digit code)", max_length=2)
    local_component = forms.ChoiceField(label="Local tax component", choices=[("sgst", "SGST"), ("utgst", "UTGST")])
    inclusive = forms.BooleanField(label="Order price includes tax", required=False)
    discount = forms.DecimalField(max_digits=15, decimal_places=2, min_value=0, initial=0)
    freight = forms.DecimalField(max_digits=15, decimal_places=2, min_value=0, initial=0)
    round_off = forms.DecimalField(max_digits=5, decimal_places=2, initial=0)

    purchase_unit_price = forms.DecimalField(label="Supplier invoice unit price", max_digits=14, decimal_places=4,
                                             min_value=0, required=False)
    supplier_invoice_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), required=False)

    def __init__(self, *args, workspace, purchase=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not purchase:
            self.fields.pop("purchase_unit_price")
            self.fields.pop("supplier_invoice_date")
        self.fields["registration_id"].choices = [
            (registration.pk, registration.gstin)
            for registration in CompanyGSTRegistration.objects.filter(workspace=workspace).order_by("gstin")
        ]


class InvoicePostingDateForm(forms.Form):
    posting_on = forms.DateField(label="Posting date", widget=forms.DateInput(attrs={"type": "date"}))


class InvoiceIssueForm(InvoicePostingDateForm):
    confirmed_total = forms.DecimalField(max_digits=15, decimal_places=2, min_value=0)
    supplier_reference = forms.CharField(max_length=16)
    recoverable_input_tax = forms.TypedChoiceField(
        label="Purchase input-tax treatment", choices=[("", "Select treatment"), ("yes", "Recoverable"),
                                                       ("no", "Include in cost")], coerce=lambda value: value == "yes",
    )

    def __init__(self, *args, workspace, draft, **kwargs):
        super().__init__(*args, **kwargs)
        self.draft = draft
        self.purchase = draft.kind == InvoiceDraft.Kind.PURCHASE
        if not self.purchase:
            self.fields.pop("supplier_reference")
            self.fields.pop("recoverable_input_tax")
        self.plans = {
            treatment: plan_invoice_posting(draft, recoverable_input_tax=treatment)
            for treatment in ((True, False) if self.purchase else (None,))
        }
        ledgers = Ledger.objects.filter(workspace=workspace, group__workspace=workspace)
        roles = dict.fromkeys(role for plan in self.plans.values() for role, _, _ in plan)
        for role in roles:
            self.fields[role] = forms.ModelChoiceField(
                ledgers.filter(group__kind__in=INVOICE_LEDGER_KINDS[role]),
                label=f"{role.replace('_', ' ').capitalize()} ledger", required=False,
            )

    def clean(self):
        cleaned = super().clean()
        if self.purchase and "recoverable_input_tax" not in cleaned:
            return cleaned
        ledger_ids = {}
        for role, _, _ in self.plans[cleaned.get("recoverable_input_tax")]:
            ledger = cleaned.get(role)
            if ledger is None:
                if role not in self.errors:
                    self.add_error(role, "Choose a ledger for the selected treatment.")
            else:
                ledger_ids[role] = ledger.pk
        cleaned["ledger_ids"] = ledger_ids
        return cleaned


class InvoiceCancelForm(InvoicePostingDateForm):
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))


class InvoiceReturnForm(InvoiceCancelForm):
    quantity = forms.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"))
    submission_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid4)
