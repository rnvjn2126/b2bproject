from django import forms

from .models import CompanyGSTRegistration, TaxRate


class RegistrationForm(forms.ModelForm):
    class Meta:
        model = CompanyGSTRegistration
        fields = ("gstin", "registered_name", "registered_address")


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
