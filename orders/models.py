from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models
from django.db.models import Q

from dashboard.models import Product


class SalesOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        CANCELLED = "cancelled", "Cancelled"

    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    source_quote = models.OneToOneField("dashboard.Quote", on_delete=models.PROTECT, related_name="sales_order")
    quotation_number = models.CharField(max_length=32)
    quotation_revision = models.PositiveSmallIntegerField()
    customer = models.ForeignKey("dashboard.Customer", on_delete=models.PROTECT)
    customer_name = models.CharField(max_length=160)
    customer_address = models.TextField(blank=True)
    customer_reference = models.CharField(max_length=100, blank=True)
    delivery_on = models.DateField(null=True, blank=True)
    payment_terms = models.TextField(blank=True)
    delivery_terms = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    approved_at = models.DateTimeField(null=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+")
    cancelled_at = models.DateTimeField(null=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+")
    cancellation_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "quotation_number"], name="order_unique_quote_series"),
        ]

    @property
    def number(self):
        return f"SO-{self.pk}"

    @property
    def subtotal(self):
        return sum((line.total for line in self.lines.all()), Decimal(0))


class SalesOrderLine(models.Model):
    order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="lines")
    quote_line = models.OneToOneField("dashboard.QuoteLine", on_delete=models.PROTECT)
    description = models.CharField(max_length=160)
    grade = models.CharField(max_length=100, blank=True)
    dimensions = models.CharField(max_length=160, blank=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit = models.CharField(max_length=12, choices=Product.Unit.choices)
    unit_price = models.DecimalField(max_digits=14, decimal_places=4)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0, unit_price__gt=0), name="order_valid_sale_line"),
        ]

    @property
    def total(self):
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class PurchaseOrder(models.Model):
    requirement = models.ForeignKey(SalesOrderLine, on_delete=models.PROTECT, related_name="purchases")
    offer = models.ForeignKey("dashboard.SupplierOffer", on_delete=models.PROTECT)
    supplier = models.ForeignKey("dashboard.Supplier", on_delete=models.PROTECT)
    supplier_name = models.CharField(max_length=160)
    supplier_reference = models.CharField(max_length=100, blank=True)
    delivery_on = models.DateField()
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_price = models.DecimalField(max_digits=14, decimal_places=4)
    submission_key = models.UUIDField(editable=False)
    status = models.CharField(max_length=10, choices=SalesOrder.Status.choices, default=SalesOrder.Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    approved_at = models.DateTimeField(null=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+")
    cancelled_at = models.DateTimeField(null=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+")
    cancellation_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["requirement", "submission_key"], name="order_unique_purchase_request"),
            models.CheckConstraint(condition=Q(quantity__gt=0, unit_price__gt=0), name="order_valid_purchase_line"),
        ]

    @property
    def number(self):
        return f"PO-{self.pk}"

    @property
    def total(self):
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class OrderMovement(models.Model):
    sales_line = models.ForeignKey(SalesOrderLine, null=True, on_delete=models.PROTECT, related_name="dispatches")
    purchase_order = models.ForeignKey(PurchaseOrder, null=True, on_delete=models.PROTECT, related_name="receipts")
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    date = models.DateField()
    reference = models.CharField(max_length=100)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0) & (
                Q(sales_line__isnull=False, purchase_order__isnull=True)
                | Q(sales_line__isnull=True, purchase_order__isnull=False)
            ), name="order_movement_one_source"),
            models.UniqueConstraint(fields=["sales_line", "reference"], name="order_unique_dispatch_ref"),
            models.UniqueConstraint(fields=["purchase_order", "reference"], name="order_unique_receipt_ref"),
        ]
