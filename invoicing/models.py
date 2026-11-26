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
    posting_on = models.DateField()
    journal = models.OneToOneField("accounting.Journal", on_delete=models.PROTECT)
    total = models.DecimalField(max_digits=15, decimal_places=2)
    snapshot = models.JSONField()
    ledger_ids = models.JSONField()
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    issued_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def number_for(start_year, sequence):
        return f"INT-SI-{start_year}-{sequence}"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "year", "sequence"], name="invoicing_unique_issue_number"),
            models.CheckConstraint(condition=Q(sequence__gt=0, total__gt=0), name="invoicing_valid_issued_invoice"),
        ]
