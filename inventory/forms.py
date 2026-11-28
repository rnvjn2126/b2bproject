from decimal import Decimal
from uuid import uuid4

from django import forms

from accounting.models import AccountGroup, JournalLine, Ledger
from dashboard.models import Product, Supplier
from invoicing.models import InvoiceDraft, IssuedInvoice

from .costing import CostMethod
from .cutting import MAX_CUT_OUTPUTS
from .landed_costs import eligible_expense_lines
from .models import LandedCharge, PurchaseCost, ReservationAction, SteelSpecification, StockCutOutput, StockLot, StockMovement, StockPosition, StorageLocation, Warehouse
from .reconciliation import stock_asset_ledgers
from .reports import company_positions


DATE_WIDGET = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})
POSITIVE = Decimal("0.001")


class CompanyForm(forms.Form):
    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        products = Product.objects.filter(owner_id=workspace.owner_id)
        locations = StorageLocation.objects.filter(warehouse__workspace=workspace).select_related("warehouse")
        scoped = {
            "product_id": products,
            "supplier_id": Supplier.objects.filter(owner_id=workspace.owner_id),
            "warehouse_id": Warehouse.objects.filter(workspace=workspace),
            "lot_id": StockLot.objects.filter(workspace=workspace, product__in=products).select_related("product"),
            "location_id": locations,
            "source_id": locations,
            "destination_id": locations,
        }
        for name in self.fields.keys() & scoped.keys():
            self.fields[name].queryset = scoped[name]

    def arguments(self):
        """Pass already scoped model selections as primary keys to the services."""
        return {name: value.pk if isinstance(self.fields[name], forms.ModelChoiceField) and value else value
                for name, value in self.cleaned_data.items()}


class SpecificationForm(CompanyForm):
    product_id = forms.ModelChoiceField(Product.objects.none(), label="Catalogue product")
    profile = forms.ChoiceField(choices=SteelSpecification.Profile.choices)
    grade = forms.CharField(max_length=100, required=False, help_text="Uses the catalogue grade when left blank.")
    density_kg_m3 = forms.DecimalField(label="Density (kg/m³)", min_value=POSITIVE, max_digits=9, decimal_places=3)
    length_mm = forms.DecimalField(label="Length per piece (mm)", required=False, max_digits=10, decimal_places=3)
    diameter_mm = forms.DecimalField(label="Outside or nominal diameter (mm)", required=False, max_digits=10, decimal_places=3)
    width_mm = forms.DecimalField(label="Overall width or first leg (mm)", required=False, max_digits=10, decimal_places=3)
    depth_mm = forms.DecimalField(label="Section depth or second leg (mm)", required=False, max_digits=10, decimal_places=3)
    thickness_mm = forms.DecimalField(label="Thickness, wall or web (mm)", required=False, max_digits=10, decimal_places=3)
    flange_mm = forms.DecimalField(label="Flange thickness (mm)", required=False, max_digits=10, decimal_places=3)


class WarehouseForm(CompanyForm):
    code = forms.CharField(max_length=24)
    name = forms.CharField(max_length=100)


class LocationForm(WarehouseForm):
    warehouse_id = forms.ModelChoiceField(Warehouse.objects.none(), label="Warehouse")


class LotForm(CompanyForm):
    product_id = forms.ModelChoiceField(Product.objects.none(), label="Catalogue product")
    code = forms.CharField(max_length=24)
    heat_number = forms.CharField(max_length=100, required=False)
    batch_number = forms.CharField(max_length=100, required=False)
    mill_name = forms.CharField(max_length=100, required=False)
    manufacturer_name = forms.CharField(max_length=100, required=False)


class StockEntryForm(CompanyForm):
    posted_on = forms.DateField(widget=DATE_WIDGET)
    reference = forms.CharField(max_length=100)
    submission_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid4)


class MovementForm(StockEntryForm):
    kind = forms.ChoiceField(choices=StockMovement.Kind.choices)
    lot_id = forms.ModelChoiceField(StockLot.objects.none(), label="Lot")
    source_id = forms.ModelChoiceField(StorageLocation.objects.none(), required=False, label="Source")
    destination_id = forms.ModelChoiceField(StorageLocation.objects.none(), required=False, label="Destination")
    quantity = forms.DecimalField(min_value=POSITIVE, max_digits=14, decimal_places=3)
    actual_kg = forms.DecimalField(label="Measured weight (kg)", required=False,
                                  min_value=Decimal("0.000001"), max_digits=18, decimal_places=6)
    order_movement_id = forms.IntegerField(required=False, min_value=1, label="Order movement ID")


class ReservationForm(StockEntryForm):
    position_id = forms.ModelChoiceField(StockPosition.objects.none(), label="Lot and storage position")
    quantity = forms.DecimalField(min_value=POSITIVE, max_digits=14, decimal_places=3)

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, workspace=workspace, **kwargs)
        self.fields["position_id"].queryset = company_positions(workspace).filter(on_hand__gt=0)
        self.fields["position_id"].label_from_instance = lambda position: f"{position.lot} · {position.location}"


class ReservationActionForm(StockEntryForm):
    kind = forms.ChoiceField(choices=ReservationAction.Kind.choices)
    quantity = forms.DecimalField(min_value=POSITIVE, max_digits=14, decimal_places=3)
    actual_kg = forms.DecimalField(label="Measured weight (kg)", required=False,
                                  min_value=Decimal("0.000001"), max_digits=18, decimal_places=6)
    order_movement_id = forms.IntegerField(required=False, min_value=1, label="Order movement ID")


class CountForm(StockEntryForm):
    lot_id = forms.ModelChoiceField(StockLot.objects.none(), label="Lot")
    location_id = forms.ModelChoiceField(StorageLocation.objects.none(), label="Location")
    counted = forms.DecimalField(min_value=0, max_digits=14, decimal_places=3, label="Counted quantity")


class ReorderForm(CompanyForm):
    warehouse_id = forms.ModelChoiceField(Warehouse.objects.none(), label="Warehouse")
    product_id = forms.ModelChoiceField(Product.objects.none(), label="Catalogue product")
    minimum_available = forms.DecimalField(min_value=0, max_digits=14, decimal_places=3)


class CertificateForm(forms.Form):
    certificate = forms.FileField(widget=forms.ClearableFileInput(attrs={"accept": ".pdf"}))


class DailyRateForm(CompanyForm):
    supplier_id = forms.ModelChoiceField(Supplier.objects.none(), label="Supplier")
    product_id = forms.ModelChoiceField(Product.objects.none(), label="Catalogue product")
    unit = forms.ChoiceField(choices=Product.Unit.choices)
    quoted_on = forms.DateField(widget=DATE_WIDGET)
    valid_through = forms.DateField(widget=DATE_WIDGET)
    unit_price = forms.DecimalField(label="Material price per unit (INR)", min_value=Decimal("0.0001"),
                                    max_digits=14, decimal_places=4)
    available_quantity = forms.DecimalField(min_value=0, max_digits=14, decimal_places=3)
    freight = forms.DecimalField(label="Quoted freight (INR)", min_value=0, max_digits=15, decimal_places=2, initial=0)
    packaging = forms.DecimalField(label="Quoted packaging (INR)", min_value=0, max_digits=15, decimal_places=2, initial=0)
    delivery_days = forms.IntegerField(label="Delivery lead time (days)", min_value=0, max_value=365)
    reference = forms.CharField(max_length=100, label="Source reference")
    submission_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid4)


class ProcurementPlanForm(CompanyForm):
    product_id = forms.ModelChoiceField(Product.objects.none(), label="Catalogue product")
    quantity = forms.DecimalField(label="Required quantity in the catalogue unit", min_value=POSITIVE,
                                  max_digits=14, decimal_places=3)
    max_delivery_days = forms.IntegerField(label="Maximum delivery lead time", min_value=0, max_value=365, required=False)


class ValuationMethodForm(CompanyForm):
    method = forms.ChoiceField(choices=CostMethod.choices)


class ValueMovementForm(CompanyForm):
    movement_id = forms.ModelChoiceField(StockMovement.objects.none(), label="Unvalued stock movement")
    material = forms.DecimalField(label="Material cost (INR)", required=False, min_value=0, max_digits=15, decimal_places=2)
    freight = forms.DecimalField(label="Freight (INR)", min_value=0, max_digits=15, decimal_places=2, initial=0)
    packaging = forms.DecimalField(label="Packaging (INR)", min_value=0, max_digits=15, decimal_places=2, initial=0)
    other = forms.DecimalField(label="Other cost (INR)", min_value=0, max_digits=15, decimal_places=2, initial=0)

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, workspace=workspace, **kwargs)
        self.fields["movement_id"].queryset = StockMovement.objects.filter(
            workspace=workspace, lot__workspace=workspace, lot__product__owner_id=workspace.owner_id,
            valuation__isnull=True,
        ).select_related("lot__product").order_by("posted_on", "pk")
        self.fields["movement_id"].label_from_instance = lambda movement: (
            f"{movement.posted_on} · {movement.get_kind_display()} · {movement.lot} · "
            f"{movement.quantity:g} {movement.lot.unit} · {movement.reference}"
        )


class StockReconciliationForm(CompanyForm):
    ledger_id = forms.ModelChoiceField(Ledger.objects.none(), label="Inventory asset ledger")
    as_of = forms.DateField(widget=DATE_WIDGET)

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, workspace=workspace, **kwargs)
        self.fields["ledger_id"].queryset = stock_asset_ledgers(workspace)


class InvoiceStockCostForm(CompanyForm):
    invoice_kind = InvoiceDraft.Kind.PURCHASE
    invoice_id = forms.ModelChoiceField(IssuedInvoice.objects.none(), label="Issued invoice")
    inventory_ledger_id = forms.ModelChoiceField(Ledger.objects.none(), label="Inventory asset ledger")

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, workspace=workspace, **kwargs)
        self.fields["invoice_id"].queryset = IssuedInvoice.objects.filter(
            workspace=workspace, kind=self.invoice_kind, cancellation__isnull=True, journal__sealed=True,
        ).order_by("-posting_on", "-pk")
        self.fields["inventory_ledger_id"].queryset = stock_asset_ledgers(workspace)


class SaleStockCostForm(InvoiceStockCostForm):
    invoice_kind = InvoiceDraft.Kind.SALES
    expense_ledger_id = forms.ModelChoiceField(Ledger.objects.none(), label="Cost-of-sales expense ledger")

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, workspace=workspace, **kwargs)
        self.fields["expense_ledger_id"].queryset = Ledger.objects.filter(
            workspace=workspace, group__workspace=workspace, group__kind=AccountGroup.Kind.EXPENSE,
        )


class CutStockForm(StockEntryForm):
    lot_id = forms.ModelChoiceField(StockLot.objects.none(), label="Input lot")
    source_id = forms.ModelChoiceField(StorageLocation.objects.none(), label="Input location")
    quantity = forms.DecimalField(label="Input quantity", min_value=POSITIVE, max_digits=14, decimal_places=3)
    actual_kg = forms.DecimalField(label="Measured input weight (kg)", min_value=Decimal("0.000001"),
                                   max_digits=18, decimal_places=6)


class CutOutputForm(CompanyForm):
    kind = forms.ChoiceField(choices=StockCutOutput.Kind.choices)
    lot_id = forms.ModelChoiceField(StockLot.objects.none(), label="Output lot")
    location_id = forms.ModelChoiceField(StorageLocation.objects.none(), label="Output location")
    quantity = forms.DecimalField(min_value=POSITIVE, max_digits=14, decimal_places=3)
    actual_kg = forms.DecimalField(label="Measured output weight (kg)", min_value=Decimal("0.000001"),
                                   max_digits=18, decimal_places=6)


CutOutputs = forms.formset_factory(CutOutputForm, extra=3, max_num=MAX_CUT_OUTPUTS, validate_max=True)


class LandedChargeForm(CompanyForm):
    kind = forms.ChoiceField(choices=LandedCharge.Kind.choices)
    posted_on = forms.DateField(widget=DATE_WIDGET)
    source_line_id = forms.ModelChoiceField(JournalLine.objects.none(), label="Posted expense debit")
    purchase_ids = forms.ModelMultipleChoiceField(PurchaseCost.objects.none(), label="Capitalised receipts",
                                                   widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, workspace=workspace, **kwargs)
        self.fields["source_line_id"].queryset = eligible_expense_lines(workspace).filter(landed_charge__isnull=True)
        self.fields["source_line_id"].label_from_instance = lambda line: (
            f"{line.journal.date} · {line.journal.reference} · {line.ledger.name} · INR {line.amount}"
        )
        self.fields["purchase_ids"].queryset = PurchaseCost.objects.filter(
            invoice__workspace=workspace, invoice__returns__isnull=True, invoice__cancellation__isnull=True,
        ).select_related("invoice").order_by("-invoice__posting_on", "-pk")
        self.fields["purchase_ids"].label_from_instance = lambda cost: str(cost.invoice)

    def arguments(self):
        return {
            "source_line_id": self.cleaned_data["source_line_id"].pk,
            "purchase_ids": [purchase.pk for purchase in self.cleaned_data["purchase_ids"]],
            "kind": self.cleaned_data["kind"],
            "posted_on": self.cleaned_data["posted_on"],
        }
