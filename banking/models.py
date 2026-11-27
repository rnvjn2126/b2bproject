from django.db import models
from django.db.models import Q


class FundsAccount(models.Model):
    class Kind(models.TextChoices):
        BANK = "bank", "Bank"
        CASH = "cash", "Cash"
        PETTY = "petty", "Petty cash"

    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    ledger = models.OneToOneField("accounting.Ledger", on_delete=models.PROTECT, related_name="funds_account")
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=5, choices=Kind.choices)
    last_four = models.CharField(max_length=4, blank=True)

    def __str__(self):
        return f"{self.name} · •••• {self.last_four}" if self.last_four else self.name

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "name"], name="banking_unique_funds_name"),
            models.CheckConstraint(
                condition=Q(kind="bank") | Q(kind__in=("cash", "petty"), last_four=""),
                name="banking_valid_funds_kind",
            ),
        ]
