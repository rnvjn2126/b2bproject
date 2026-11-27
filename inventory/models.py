from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from dashboard.models import Product

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
