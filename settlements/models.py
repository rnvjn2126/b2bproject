from django.conf import settings
from django.db import models


class InvoiceDueDate(models.Model):
    invoice = models.OneToOneField("invoicing.IssuedInvoice", on_delete=models.PROTECT, related_name="due_date")
    due_on = models.DateField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)
