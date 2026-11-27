from django.conf import settings
from django.db import models
from django.db.models import Q


class InvoiceDueDate(models.Model):
    invoice = models.OneToOneField("invoicing.IssuedInvoice", on_delete=models.PROTECT, related_name="due_date")
    due_on = models.DateField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)


class PartyPayment(models.Model):
    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    customer = models.ForeignKey("dashboard.Customer", on_delete=models.PROTECT, null=True)
    supplier = models.ForeignKey("dashboard.Supplier", on_delete=models.PROTECT, null=True)
    journal = models.OneToOneField("accounting.Journal", on_delete=models.PROTECT)
    funds_ledger = models.ForeignKey("accounting.Ledger", on_delete=models.PROTECT, related_name="+")
    control_ledger = models.ForeignKey("accounting.Ledger", on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    external_reference = models.CharField(max_length=100, blank=True)
    submission_key = models.UUIDField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(Q(customer__isnull=False, supplier__isnull=True)
                           | Q(customer__isnull=True, supplier__isnull=False))
                & Q(amount__gt=0) & ~Q(funds_ledger=models.F("control_ledger")),
                name="settlements_valid_party_payment",
            ),
            models.UniqueConstraint(fields=["workspace", "submission_key"], name="settlements_unique_payment_key"),
            models.UniqueConstraint(fields=["workspace", "funds_ledger", "external_reference"],
                                    condition=~Q(external_reference=""), name="settlements_unique_payment_reference"),
        ]
