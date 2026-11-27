from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

from .tax import validate_gstin


class CompanyGSTRegistration(models.Model):
    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    gstin = models.CharField(max_length=15, validators=[validate_gstin])
    registered_name = models.CharField(max_length=160)
    registered_address = models.TextField()
    letterhead = models.CharField(max_length=240, blank=True)
    logo_png = models.BinaryField(default=bytes, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "gstin"], name="invoicing_unique_company_gstin"),
        ]


class TaxRate(models.Model):
    class ItemKind(models.TextChoices):
        GOODS = "goods", "HSN"
        SERVICE = "service", "SAC"

    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    item_kind = models.CharField(max_length=7, choices=ItemKind.choices)
    item_code = models.CharField(max_length=8, validators=[RegexValidator(r"\A(?:\d{4}|\d{6}|\d{8})\Z")])
    effective_from = models.DateField()
    source_url = models.URLField()
    integrated_rate = models.DecimalField(max_digits=7, decimal_places=4)
    central_rate = models.DecimalField(max_digits=7, decimal_places=4)
    local_rate = models.DecimalField(max_digits=7, decimal_places=4)
    cess_rate = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal(0),
        validators=[MinValueValidator(Decimal(0)), MaxValueValidator(Decimal(100))],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "item_kind", "item_code", "effective_from"],
                                    name="invoicing_unique_rate_version"),
            models.CheckConstraint(
                condition=Q(integrated_rate__range=(0, 100), central_rate__range=(0, 100),
                            local_rate__range=(0, 100), cess_rate__range=(0, 100)),
                name="invoicing_valid_rate_components",
            ),
        ]

    def clean(self):
        if self.item_kind == self.ItemKind.SERVICE and len(self.item_code) != 6:
            raise ValidationError({"item_code": "Enter the six-digit SAC code."})

    @classmethod
    def effective_for(cls, workspace, item_kind, item_code, supply_date):
        return cls.objects.filter(workspace=workspace, item_kind=item_kind, item_code=item_code,
                                  effective_from__lte=supply_date).order_by("-effective_from").first()


class InvoiceDraft(models.Model):
    class Kind(models.TextChoices):
        SALES = "sales", "Sales"
        PURCHASE = "purchase", "Purchase"

    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    movement = models.OneToOneField("orders.OrderMovement", on_delete=models.PROTECT)
    registration = models.ForeignKey(CompanyGSTRegistration, on_delete=models.PROTECT)
    rate = models.ForeignKey(TaxRate, on_delete=models.PROTECT)
    kind = models.CharField(max_length=8, choices=Kind.choices)
    supply_on = models.DateField()
    total = models.DecimalField(max_digits=24, decimal_places=2)
    snapshot = models.JSONField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(total__gte=0), name="invoicing_draft_nonnegative_total"),
        ]


class IssuedInvoice(models.Model):
    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    draft = models.OneToOneField(InvoiceDraft, on_delete=models.PROTECT)
    year = models.ForeignKey("accounting.FinancialYear", on_delete=models.PROTECT)
    sequence = models.PositiveBigIntegerField()
    number = models.CharField(max_length=32)
    kind = models.CharField(max_length=8, choices=InvoiceDraft.Kind.choices, default=InvoiceDraft.Kind.SALES)
    posting_on = models.DateField()
    supplier_invoice_date = models.DateField(null=True)
    supplier_reference = models.CharField(max_length=16, blank=True)
    supplier_gstin = models.CharField(max_length=15, blank=True)
    supplier_year = models.PositiveSmallIntegerField(null=True)
    recoverable_input_tax = models.BooleanField(null=True)
    journal = models.OneToOneField("accounting.Journal", on_delete=models.PROTECT)
    total = models.DecimalField(max_digits=15, decimal_places=2)
    snapshot = models.JSONField()
    ledger_ids = models.JSONField()
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    issued_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def number_for(kind, start_year, sequence):
        series = "SI" if kind == InvoiceDraft.Kind.SALES else "PI"
        return f"INT-{series}-{start_year}-{sequence}"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "year", "sequence"], name="invoicing_unique_issue_number"),
            models.CheckConstraint(condition=Q(sequence__gt=0, total__gt=0), name="invoicing_valid_issued_invoice"),
            models.UniqueConstraint(fields=["workspace", "supplier_gstin", "supplier_year", "supplier_reference"],
                                    condition=Q(kind="purchase"), name="invoicing_unique_supplier_document"),
            models.CheckConstraint(
                condition=(
                    Q(kind="sales", supplier_invoice_date__isnull=True, supplier_reference="", supplier_gstin="",
                      supplier_year__isnull=True, recoverable_input_tax__isnull=True)
                    | (Q(kind="purchase", supplier_invoice_date__isnull=False, supplier_year__isnull=False,
                         recoverable_input_tax__isnull=False, supplier_invoice_date__lte=models.F("posting_on"))
                       & ~Q(supplier_reference="") & ~Q(supplier_gstin=""))
                ), name="invoicing_valid_supplier_document",
            ),
        ]


class InvoiceCancellation(models.Model):
    invoice = models.OneToOneField(IssuedInvoice, on_delete=models.PROTECT, related_name="cancellation")
    reversal = models.OneToOneField("accounting.Journal", on_delete=models.PROTECT)
    reason = models.CharField(max_length=500)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    cancelled_at = models.DateTimeField(auto_now_add=True)


class InvoiceReturn(models.Model):
    invoice = models.ForeignKey(IssuedInvoice, on_delete=models.PROTECT, related_name="returns")
    journal = models.OneToOneField("accounting.Journal", on_delete=models.PROTECT)
    sequence = models.PositiveIntegerField()
    submission_key = models.UUIDField()
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    reason = models.CharField(max_length=500)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["invoice", "sequence"], name="invoicing_unique_return_number"),
            models.UniqueConstraint(fields=["invoice", "submission_key"], name="invoicing_unique_return_submission"),
            models.CheckConstraint(condition=Q(quantity__gt=0, amount__gt=0, sequence__gt=0),
                                   name="invoicing_valid_return_amount"),
        ]
