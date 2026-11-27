from django.conf import settings
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


class ReportedInstrument(models.Model):
    class Method(models.TextChoices):
        UPI = "upi", "UPI"
        NEFT = "neft", "NEFT"
        RTGS = "rtgs", "RTGS"
        IMPS = "imps", "IMPS"
        CHEQUE = "cheque", "Cheque"

    class Direction(models.TextChoices):
        INFLOW = "in", "Inflow"
        OUTFLOW = "out", "Outflow"

    account = models.ForeignKey(FundsAccount, on_delete=models.PROTECT)
    journal_line = models.OneToOneField("accounting.JournalLine", on_delete=models.PROTECT, null=True)
    method = models.CharField(max_length=6, choices=Method.choices)
    direction = models.CharField(max_length=3, choices=Direction.choices)
    reference = models.CharField(max_length=80)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    reported_on = models.DateField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="banking_positive_instrument"),
            models.UniqueConstraint(fields=["account", "method", "direction", "reference"],
                                    name="banking_unique_reported_reference"),
        ]


class ChequeEvent(models.Model):
    class State(models.TextChoices):
        PRESENTED = "presented", "Reported presented"
        CLEARED = "cleared", "Reported cleared"
        RETURNED = "returned", "Reported returned"

    instrument = models.ForeignKey(ReportedInstrument, on_delete=models.PROTECT, related_name="cheque_events")
    state = models.CharField(max_length=9, choices=State.choices)
    happened_on = models.DateField()
    reason = models.CharField(max_length=250, blank=True)
    submission_key = models.UUIDField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["happened_on", "id"]
        constraints = [
            models.UniqueConstraint(fields=["instrument", "submission_key"], name="banking_unique_cheque_event"),
        ]
