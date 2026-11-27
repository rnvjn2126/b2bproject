from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from dashboard.models import Customer, Supplier


class StatementFilter(forms.Form):
    as_of = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False)
    supplier = forms.ModelChoiceField(queryset=Supplier.objects.none(), required=False)

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.filter(owner_id=workspace.owner_id)
        self.fields["supplier"].queryset = Supplier.objects.filter(owner_id=workspace.owner_id)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("customer") and cleaned.get("supplier"):
            raise ValidationError("Choose a customer or a supplier for a party statement.")
        if cleaned.get("as_of") and cleaned["as_of"] > timezone.localdate():
            self.add_error("as_of", "Choose today or a past date.")
        return cleaned
