import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class WorkspaceCode(models.Model):
    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    code = models.CharField(max_length=24)
    name = models.CharField(max_length=120)

    class Meta:
        abstract = True
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "code"], name="unique_%(app_label)s_%(class)s_code"),
        ]

    def __str__(self):
        return f"{self.code} · {self.name}"


class AccountGroup(WorkspaceCode):
    class Kind(models.TextChoices):
        ASSET = "asset", "Asset"
        LIABILITY = "liability", "Liability"
        EQUITY = "equity", "Equity"
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"

    kind = models.CharField(max_length=12, choices=Kind.choices)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)


class Ledger(WorkspaceCode):
    group = models.ForeignKey(AccountGroup, on_delete=models.PROTECT)


class Branch(WorkspaceCode):
    pass


class CostCentre(WorkspaceCode):
    pass


class FinancialYear(models.Model):
    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    start_year = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["-start_year"]
        constraints = [models.UniqueConstraint(fields=["workspace", "start_year"], name="accounting_unique_year")]

    def __str__(self):
        return f"{self.start_year}–{self.start_year + 1}"


class Period(models.Model):
    year = models.ForeignKey(FinancialYear, on_delete=models.PROTECT, related_name="periods")
    starts_on = models.DateField()
    ends_before = models.DateField()
    locked_at = models.DateTimeField(null=True)
    locked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)

    class Meta:
        ordering = ["starts_on"]
        constraints = [
            models.UniqueConstraint(fields=["year", "starts_on"], name="accounting_unique_period"),
            models.CheckConstraint(condition=Q(ends_before__gt=models.F("starts_on")), name="accounting_period_date_order"),
        ]


class Journal(models.Model):
    class Kind(models.TextChoices):
        GENERAL = "general", "General journal"
        OPENING = "opening", "Opening balances"
        ADJUSTMENT = "adjustment", "Adjustment"
        RECEIPT = "receipt", "Receipt voucher"
        PAYMENT = "payment", "Payment voucher"
        CONTRA = "contra", "Contra voucher"
        SALES = "sales", "Sales voucher"
        PURCHASE = "purchase", "Purchase voucher"
        DEBIT_NOTE = "debit_note", "Debit note"
        CREDIT_NOTE = "credit_note", "Credit note"
        REVERSAL = "reversal", "Reversal"

    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    period = models.ForeignKey(Period, on_delete=models.PROTECT)
    date = models.DateField()
    kind = models.CharField(max_length=12, choices=Kind.choices)
    reference = models.CharField(max_length=100, blank=True)
    narration = models.CharField(max_length=500)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.PROTECT)
    cost_centre = models.ForeignKey(CostCentre, null=True, blank=True, on_delete=models.PROTECT)
    reverses = models.OneToOneField("self", null=True, blank=True, related_name="reversal", on_delete=models.PROTECT)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    posted_at = models.DateTimeField(auto_now_add=True)
    submission_key = models.UUIDField(default=uuid.uuid4, editable=False)
    fingerprint = models.CharField(max_length=64, editable=False)
    sealed = models.BooleanField(default=False, editable=False)

    @property
    def transaction_reference(self):
        # The database primary key gives every posted journal a stable, unique reference.
        return f"JRN-{self.pk}"

    class Meta:
        ordering = ["-date", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "submission_key"], name="accounting_unique_submission"),
            models.UniqueConstraint(fields=["workspace"], condition=Q(kind="opening"), name="accounting_one_opening"),
        ]
        indexes = [models.Index(fields=["workspace", "date"], name="accounting_journal_date")]


class JournalLine(models.Model):
    class Side(models.TextChoices):
        DEBIT = "D", "Debit"
        CREDIT = "C", "Credit"

    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, related_name="lines")
    ledger = models.ForeignKey(Ledger, on_delete=models.PROTECT, related_name="lines")
    side = models.CharField(max_length=1, choices=Side.choices)
    amount = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0, side__in=["D", "C"]), name="accounting_valid_line"),
        ]


class VoucherDraft(models.Model):
    workspace = models.ForeignKey("dashboard.BusinessAccount", on_delete=models.PROTECT)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(max_length=12, choices=Journal.Kind.choices)
    date = models.DateField()
    reference = models.CharField(max_length=100, blank=True)
    narration = models.CharField(max_length=500)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.PROTECT)
    cost_centre = models.ForeignKey(CostCentre, null=True, blank=True, on_delete=models.PROTECT)
    # Draft-only payload. Posted data lives in the sealed, relational journal.
    allocations = models.JSONField()
    revision = models.PositiveIntegerField(default=1)
    posting_key = models.UUIDField(default=uuid.uuid4, editable=False)
    journal = models.OneToOneField(Journal, null=True, on_delete=models.PROTECT, related_name="voucher_draft")

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "posting_key"], name="accounting_unique_draft_key"),
        ]

    @property
    def number(self):
        return f"VCH-{self.pk}"
