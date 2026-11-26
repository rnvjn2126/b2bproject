from decimal import Decimal

from django import forms
from django.forms import formset_factory

from .models import AccountGroup, Branch, CostCentre, Journal, JournalLine, Ledger


class YearForm(forms.Form):
    start_year = forms.IntegerField(label="Financial year start", min_value=1900, max_value=9998)


class PostingForm(forms.Form):
    date = forms.DateField(widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    reference = forms.CharField(max_length=100, required=False)
    narration = forms.CharField(max_length=500)
    submission_key = forms.UUIDField(widget=forms.HiddenInput)


class JournalForm(PostingForm):
    kind = forms.ChoiceField(choices=[(value, label) for value, label in Journal.Kind.choices if value != Journal.Kind.REVERSAL])
    branch = forms.ModelChoiceField(queryset=Branch.objects.none(), required=False)
    cost_centre = forms.ModelChoiceField(queryset=CostCentre.objects.none(), required=False)

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branch"].queryset = Branch.objects.filter(workspace=workspace)
        self.fields["cost_centre"].queryset = CostCentre.objects.filter(workspace=workspace)


class JournalLineForm(forms.Form):
    ledger = forms.ModelChoiceField(queryset=Ledger.objects.none())
    side = forms.ChoiceField(choices=[("", "Choose a side"), *JournalLine.Side.choices])
    amount = forms.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal("0.01"))

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ledger"].queryset = Ledger.objects.filter(workspace=workspace)


JournalLines = formset_factory(JournalLineForm, extra=4, max_num=50, validate_max=True, absolute_max=50)


class ChartForm(forms.Form):
    code = forms.RegexField(r"^[A-Z0-9][A-Z0-9-]*$", max_length=24, help_text="Use uppercase letters, numbers and hyphens.")
    name = forms.CharField(max_length=120)


class GroupForm(ChartForm):
    kind = forms.ChoiceField(choices=AccountGroup.Kind.choices)
    parent = forms.ModelChoiceField(queryset=AccountGroup.objects.none(), required=False)

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = AccountGroup.objects.filter(workspace=workspace)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("parent") and cleaned["parent"].kind != cleaned.get("kind"):
            self.add_error("kind", "Choose the same account type as the parent group.")
        return cleaned


class LedgerForm(ChartForm):
    group = forms.ModelChoiceField(queryset=AccountGroup.objects.none())

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = AccountGroup.objects.filter(workspace=workspace)


class BalanceForm(forms.Form):
    start = forms.DateField(label="From", widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    end = forms.DateField(label="Through", widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    branch = forms.ModelChoiceField(queryset=Branch.objects.none(), required=False)

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branch"].queryset = Branch.objects.filter(workspace=workspace)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("start") and cleaned.get("end") and cleaned["start"] > cleaned["end"]:
            self.add_error("end", "Choose an end date on or after the start date.")
        return cleaned
