from datetime import date

from django import forms
from django.utils import timezone

from .models import FinancialYear


class FinancialReportForm(forms.Form):
    year = forms.ModelChoiceField(
        FinancialYear.objects.none(), label="Financial year", required=False,
        help_text="Selecting a year sets the report dates.",
    )
    start = forms.DateField(label="From", required=False, widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    end = forms.DateField(label="Through", required=False, widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    comparison = forms.ChoiceField(choices=(
        ("", "No comparison"), ("previous", "Previous period"), ("prior-year", "Previous year"),
    ), required=False)

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["year"].queryset = FinancialYear.objects.filter(workspace=workspace, start_year__lt=9999)

    def clean(self):
        cleaned = super().clean()
        today = timezone.localdate()
        year = cleaned.get("year")
        if year:
            start = date(year.start_year, 4, 1)
            end = min(date(year.start_year + 1, 3, 31), today)
            cleaned.update(start=start, end=end)
        else:
            start, end = cleaned.get("start"), cleaned.get("end")
        if start and end:
            if start.year < 1900 or not start <= end <= today:
                self.add_error("end", "Use dates from 1900 through today with the end on or after the start.")
        elif not self.errors:
            self.add_error(None, "Choose a financial year or enter both dates.")
        return cleaned
