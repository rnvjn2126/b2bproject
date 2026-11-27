from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from dashboard.models import Product

from .costing import CostMethod
from .geometry import MM2_PER_M2, MM_PER_M, cross_section_mm2


class SteelSpecification(models.Model):
    class Profile(models.TextChoices):
        ROUND = "round", "Round bar"
        TMT = "tmt", "TMT bar"
        SHEET = "sheet", "Sheet"
        PLATE = "plate", "Plate"
        PIPE = "pipe", "Pipe"
        COIL = "coil", "Coil"
        ANGLE = "angle", "Angle"
        CHANNEL = "channel", "Channel"
        BEAM = "beam", "Beam"

    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    product = models.OneToOneField("dashboard.Product", on_delete=models.PROTECT, related_name="steel_specification")
    profile = models.CharField(max_length=10, choices=Profile.choices)
    grade = models.CharField(max_length=100)
    density_kg_m3 = models.DecimalField(max_digits=9, decimal_places=3)
    length_mm = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    diameter_mm = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    width_mm = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    depth_mm = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    thickness_mm = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    flange_mm = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(density_kg_m3__gt=0) & Q(grade__gt="") & (
                    Q(length_mm__isnull=True) | Q(length_mm__gt=0)
                ) & (
                    Q(diameter_mm__isnull=True) | Q(diameter_mm__gt=0)
                ) & (
                    Q(width_mm__isnull=True) | Q(width_mm__gt=0)
                ) & (
                    Q(depth_mm__isnull=True) | Q(depth_mm__gt=0)
                ) & (
                    Q(thickness_mm__isnull=True) | Q(thickness_mm__gt=0)
                ) & (
                    Q(flange_mm__isnull=True) | Q(flange_mm__gt=0)
                ),
                name="inventory_positive_steel_dimensions",
            ),
        ]

    def clean(self):
        if self.product_id and self.workspace_id and self.product.owner_id != self.workspace.owner_id:
            raise ValidationError({"product": "Choose a product in this company."})
        if self.density_kg_m3 is not None and self.density_kg_m3 <= 0:
            raise ValidationError({"density_kg_m3": "Enter a positive steel density."})
        self.cross_section_mm2

    @property
    def cross_section_mm2(self):
        return cross_section_mm2(self.profile, diameter=self.diameter_mm, width=self.width_mm, depth=self.depth_mm,
                                 thickness=self.thickness_mm, flange=self.flange_mm)

    @property
    def theoretical_kg_per_m(self):
        return self.cross_section_mm2 * self.density_kg_m3 / MM2_PER_M2

    @property
    def theoretical_kg_per_piece(self):
        if self.length_mm is None:
            return None
        return self.theoretical_kg_per_m * self.length_mm / MM_PER_M


class Warehouse(models.Model):
    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    code = models.CharField(max_length=24)
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.code} · {self.name}"

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["workspace", "code"], name="inventory_unique_warehouse_code")]


class StorageLocation(models.Model):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="locations")
    code = models.CharField(max_length=24)
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.warehouse.code} / {self.code} · {self.name}"

    class Meta:
        ordering = ["warehouse__code", "code"]
        constraints = [models.UniqueConstraint(fields=["warehouse", "code"], name="inventory_unique_location_code")]


class StockLot(models.Model):
    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    product = models.ForeignKey("dashboard.Product", on_delete=models.PROTECT)
    code = models.CharField(max_length=24)
    grade = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=12, choices=Product.Unit.choices)
    heat_number = models.CharField(max_length=100, blank=True)
    batch_number = models.CharField(max_length=100, blank=True)
    mill_name = models.CharField(max_length=100, blank=True)
    manufacturer_name = models.CharField(max_length=100, blank=True)
    nominal_kg_per_m = models.DecimalField(max_digits=19, decimal_places=9, null=True, blank=True)
    length_mm = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)

    def __str__(self):
        return f"{self.code} · {self.product.name}"

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "code"], name="inventory_unique_lot_code"),
            models.CheckConstraint(
                condition=(Q(nominal_kg_per_m__isnull=True) | Q(nominal_kg_per_m__gt=0))
                & (Q(length_mm__isnull=True) | Q(length_mm__gt=0)), name="inventory_positive_nominal_weight",
            ),
        ]


class LotCertificate(models.Model):
    lot = models.OneToOneField(StockLot, on_delete=models.PROTECT, related_name="certificate")
    content = models.BinaryField()
    digest = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)


class StockPosition(models.Model):
    lot = models.ForeignKey(StockLot, on_delete=models.PROTECT, related_name="positions")
    location = models.ForeignKey(StorageLocation, on_delete=models.PROTECT, related_name="positions")
    on_hand = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    reserved = models.DecimalField(max_digits=14, decimal_places=3, default=0)

    @property
    def available(self):
        return self.on_hand - self.reserved

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["lot", "location"], name="inventory_unique_stock_position"),
            models.CheckConstraint(condition=Q(reserved__gte=0, on_hand__gte=models.F("reserved")),
                                   name="inventory_nonnegative_stock_position"),
        ]


class StockMovement(models.Model):
    class Kind(models.TextChoices):
        RECEIPT = "receipt", "Receipt"
        ISSUE = "issue", "Issue"
        TRANSFER = "transfer", "Warehouse transfer"

    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    lot = models.ForeignKey(StockLot, on_delete=models.PROTECT, related_name="movements")
    source = models.ForeignKey(StorageLocation, on_delete=models.PROTECT, related_name="+", null=True)
    destination = models.ForeignKey(StorageLocation, on_delete=models.PROTECT, related_name="+", null=True)
    order_movement = models.OneToOneField("orders.OrderMovement", on_delete=models.PROTECT, null=True,
                                         related_name="stock_movement")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    actual_kg = models.DecimalField(max_digits=18, decimal_places=6, null=True)
    theoretical_kg = models.DecimalField(max_digits=18, decimal_places=6, null=True)
    posted_on = models.DateField()
    reference = models.CharField(max_length=100)
    submission_key = models.UUIDField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["posted_on", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "submission_key"], name="inventory_unique_stock_submit"),
            models.CheckConstraint(condition=Q(quantity__gt=0) & (
                Q(kind="receipt", source__isnull=True, destination__isnull=False)
                | Q(kind="issue", source__isnull=False, destination__isnull=True)
                | (Q(kind="transfer", source__isnull=False, destination__isnull=False, order_movement__isnull=True)
                   & ~Q(source=models.F("destination")))
            ), name="inventory_valid_stock_route"),
            models.CheckConstraint(
                condition=(Q(actual_kg__isnull=True) | Q(actual_kg__gt=0))
                & (Q(theoretical_kg__isnull=True) | Q(theoretical_kg__gte=0)),
                name="inventory_valid_stock_weights",
            ),
        ]


class StockReservation(models.Model):
    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    position = models.ForeignKey(StockPosition, on_delete=models.PROTECT, related_name="reservations")
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    remaining = models.DecimalField(max_digits=14, decimal_places=3)
    posted_on = models.DateField()
    reference = models.CharField(max_length=100)
    submission_key = models.UUIDField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "submission_key"], name="inventory_unique_reserve_submit"),
            models.CheckConstraint(condition=Q(quantity__gt=0, remaining__gte=0, remaining__lte=models.F("quantity")),
                                   name="inventory_valid_reservation_quantity"),
        ]


class ReservationAction(models.Model):
    class Kind(models.TextChoices):
        RELEASE = "release", "Release"
        ISSUE = "issue", "Issue reserved stock"

    reservation = models.ForeignKey(StockReservation, on_delete=models.PROTECT, related_name="actions")
    movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, null=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    posted_on = models.DateField()
    reference = models.CharField(max_length=100)
    submission_key = models.UUIDField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["reservation", "submission_key"], name="inventory_unique_reserve_action"),
            models.CheckConstraint(condition=Q(quantity__gt=0) & (
                Q(kind="issue", movement__isnull=False) | Q(kind="release", movement__isnull=True)
            ), name="inventory_valid_reservation_action"),
        ]

class StockCount(models.Model):
    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    position = models.ForeignKey(StockPosition, on_delete=models.PROTECT, related_name="counts")
    adjustment = models.OneToOneField(StockMovement, on_delete=models.PROTECT, null=True, related_name="physical_count")
    before = models.DecimalField(max_digits=14, decimal_places=3)
    counted = models.DecimalField(max_digits=14, decimal_places=3)
    posted_on = models.DateField()
    reference = models.CharField(max_length=100)
    submission_key = models.UUIDField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "submission_key"], name="inventory_unique_count_submit"),
            models.CheckConstraint(condition=Q(before__gte=0, counted__gte=0) & (
                Q(adjustment__isnull=True, before=models.F("counted"))
                | (Q(adjustment__isnull=False) & ~Q(before=models.F("counted")))
            ), name="inventory_valid_count_adjustment"),
        ]


class ReorderPolicy(models.Model):
    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    product = models.ForeignKey("dashboard.Product", on_delete=models.PROTECT)
    unit = models.CharField(max_length=12, choices=Product.Unit.choices)
    minimum_available = models.DecimalField(max_digits=14, decimal_places=3)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "warehouse", "product"], name="inventory_unique_reorder"),
            models.CheckConstraint(condition=Q(minimum_available__gte=0), name="inventory_valid_reorder_threshold"),
        ]


class ValuationPolicy(models.Model):
    workspace = models.OneToOneField("dashboard.BusinessAccount", on_delete=models.PROTECT)
    method = models.CharField(max_length=7, choices=CostMethod.choices)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(method__in=CostMethod.values),
                                              name="inventory_valid_cost_method")]


class ValuationEvent(models.Model):
    movement = models.OneToOneField(StockMovement, related_name="valuation", on_delete=models.PROTECT)
    method = models.CharField(max_length=7, choices=CostMethod.choices)
    material = models.DecimalField(max_digits=15, decimal_places=2)
    freight = models.DecimalField(max_digits=15, decimal_places=2)
    packaging = models.DecimalField(max_digits=15, decimal_places=2)
    other = models.DecimalField(max_digits=15, decimal_places=2)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    closing_quantity = models.DecimalField(max_digits=18, decimal_places=3)
    closing_amount = models.DecimalField(max_digits=18, decimal_places=2)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(method__in=CostMethod.values, material__gte=0, freight__gte=0, packaging__gte=0,
                            other__gte=0, amount__gte=0, closing_quantity__gte=0, closing_amount__gte=0)
                & (Q(closing_quantity__gt=0) | Q(closing_amount=0)),
                name="inventory_valid_cost_event",
            ),
        ]


class ValuationLayer(models.Model):
    receipt = models.OneToOneField(ValuationEvent, related_name="cost_layer", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    amount = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gte=0, amount__gte=0) & (Q(quantity__gt=0) | Q(amount=0)),
                name="inventory_valid_cost_layer",
            ),
        ]


class SupplierDailyRate(models.Model):
    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    supplier = models.ForeignKey("dashboard.Supplier", on_delete=models.PROTECT)
    product = models.ForeignKey("dashboard.Product", on_delete=models.PROTECT)
    unit = models.CharField(max_length=12, choices=Product.Unit.choices)
    quoted_on = models.DateField()
    valid_through = models.DateField()
    unit_price = models.DecimalField(max_digits=14, decimal_places=4)
    available_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    freight = models.DecimalField(max_digits=15, decimal_places=2)
    packaging = models.DecimalField(max_digits=15, decimal_places=2)
    delivery_days = models.PositiveSmallIntegerField()
    reference = models.CharField(max_length=100)
    submission_key = models.UUIDField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-quoted_on", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "submission_key"], name="inventory_unique_rate_submission"),
            models.CheckConstraint(
                condition=Q(unit__in=Product.Unit.values, unit_price__gt=0, available_quantity__gte=0,
                            freight__gte=0, packaging__gte=0, delivery_days__lte=365, valid_through__gte=models.F("quoted_on")),
                name="inventory_valid_supplier_rate",
            ),
        ]
        indexes = [
            models.Index(fields=["workspace", "product", "supplier", "-quoted_on"], name="inventory_rate_lookup_idx"),
        ]
