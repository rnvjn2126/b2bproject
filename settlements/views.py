from decimal import Decimal
from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from accounting.views import owner_only
from dashboard.models import Customer
from invoicing.models import InvoiceDraft

from .balances import invoice_balances, unallocated_payments
from .forms import StatementFilter


def settlement_owner(view):
    @owner_only
    @never_cache
    @wraps(view)
    def guarded(request, workspace, *args, **kwargs):
        if workspace is None or not settings.INTERNAL_INVOICE_ISSUANCE:
            raise Http404
        return view(request, workspace, *args, **kwargs)
    return guarded


@settlement_owner
@require_GET
def statement(request, workspace):
    today = timezone.localdate()
    form = StatementFilter(request.GET or None, workspace=workspace, initial={"as_of": today})
    context = {"form": form}
    if form.is_bound and not form.is_valid():
        return render(request, "settlements/statement.html", context)
    data = form.cleaned_data if form.is_bound else {}
    as_of = data.get("as_of") or today
    scope = {f"{key}_id": data[key].pk for key in ("customer", "supplier") if data.get(key)}
    rows = invoice_balances(workspace, as_of, **scope)
    buckets = ("Current", "1–30", "31–60", "61–90", "Over 90", "No due date")
    ageing = {bucket: {"sales": Decimal(0), "purchase": Decimal(0)} for bucket in buckets}
    for row in rows:
        if row.outstanding > 0:
            ageing[row.bucket][row.invoice.kind] += row.outstanding
    context.update(as_of=as_of, rows=rows, ageing=ageing, payments=unallocated_payments(workspace, as_of, **scope), today=today)
    return render(request, "settlements/statement.html", context)


@settlement_owner
@require_GET
def reminder(request, workspace, pk):
    today = timezone.localdate()
    rows = invoice_balances(workspace, today, invoice_id=pk)
    if not rows:
        raise Http404
    row = rows[0]
    invoice = row.invoice
    if invoice.kind != InvoiceDraft.Kind.SALES or row.outstanding <= 0 or not row.due_on or row.due_on >= today:
        raise Http404
    party = Customer.objects.filter(owner_id=workspace.owner_id, pk=invoice.draft.movement.sales_line.order.customer_id).first()
    if party is None:
        raise Http404
    draft = (
        f"Hello {invoice.snapshot['party']['name']},\n\n"
        f"Our records show INR {row.outstanding:.2f} due on invoice {invoice.number}, "
        f"with a due date of {row.due_on:%d %b %Y}. Please let us know the payment status "
        f"or share the reference if it has already been paid.\n\n{workspace.name}"
    )
    return render(request, "settlements/reminder.html", {
        "invoice": invoice, "draft": draft,
        "whatsapp": f"{party.whatsapp_chat_url}?{urlencode({'text': draft})}" if party.whatsapp_chat_url else "",
    })
