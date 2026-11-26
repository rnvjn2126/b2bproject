from decimal import Decimal

from django import forms

from dashboard.models import SupplierOffer


class ConvertQuoteForm(forms.Form):
    customer_reference = forms.CharField(max_length=100, required=False, label="Customer purchase order reference")
    delivery_on = forms.DateField(required=False, label="Requested delivery", widget=forms.DateInput(attrs={"type": "date"}))


class CancellationForm(forms.Form):
    reason = forms.CharField(max_length=500, label="Cancellation reason")


class PurchaseForm(forms.Form):
    offer = forms.ModelChoiceField(queryset=SupplierOffer.objects.none())
    quantity = forms.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"))
    delivery_on = forms.DateField(label="Expected delivery", widget=forms.DateInput(attrs={"type": "date"}))
    supplier_reference = forms.CharField(max_length=100, required=False, label="Supplier reference")
    submission_key = forms.UUIDField(widget=forms.HiddenInput)

    def __init__(self, *args, line, **kwargs):
        super().__init__(*args, **kwargs)
        owner_id = line.order.workspace.owner_id
        self.fields["offer"].queryset = SupplierOffer.objects.filter(
            owner_id=owner_id, supplier__owner_id=owner_id, rfq_line_id=line.quote_line.rfq_line_id,
        ).select_related("supplier")
        self.fields["offer"].label_from_instance = lambda offer: (
            f"{offer.supplier} · {offer.available_quantity} {offer.unit} · {offer.delivery_days} days"
        )


class MovementForm(forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    quantity = forms.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"))
    reference = forms.CharField(max_length=100, label="Goods document reference")
