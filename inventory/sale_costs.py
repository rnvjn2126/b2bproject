from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounting.models import AccountGroup, Journal, Ledger, Period
from accounting.services import lock_books, post_journal
from invoicing.models import InvoiceDraft, InvoiceReturn, IssuedInvoice
from invoicing.tax import rounded

from .models import SaleCost, SaleCostCorrection, StockMovement, ValuationEvent
from .reconciliation import posted_asset_balance
from .stock import unvalued_stock_correction
from .valuation import value_stock_movement


def _check_enabled():
    if not settings.INTERNAL_STOCK_ACCOUNTING:
        raise PermissionDenied("Internal stock accounting is disabled.")


@transaction.atomic
def post_sale_cost(workspace, actor, *, invoice_id, inventory_ledger_id, expense_ledger_id):
    _check_enabled()
    lock_books(workspace, actor)
    invoice = IssuedInvoice.objects.filter(
        pk=invoice_id, workspace=workspace, kind=InvoiceDraft.Kind.SALES, draft__workspace=workspace,
        draft__movement__sales_line__order__workspace=workspace, journal__workspace=workspace,
        journal__sealed=True, journal__kind=Journal.Kind.SALES_INVOICE,
    ).select_related("draft__movement", "journal").first()
    if invoice is None or invoice.journal.date != invoice.posting_on:
        raise ValidationError("Choose an issued sales invoice in this company.")
    existing = SaleCost.objects.filter(invoice=invoice).first()
    if existing:
        if (existing.inventory_ledger_id, existing.expense_ledger_id) != (inventory_ledger_id, expense_ledger_id):
            raise ValidationError("This invoice was already costed using different ledgers.")
        return existing
    if hasattr(invoice, "cancellation") or invoice.returns.exists():
        raise ValidationError("Review any existing invoice corrections before posting its cost.")

    dispatch = invoice.draft.movement
    issue = ValuationEvent.objects.filter(
        movement__workspace=workspace, movement__lot__workspace=workspace,
        movement__lot__product__owner_id=workspace.owner_id, movement__kind=StockMovement.Kind.ISSUE,
        movement__order_movement=dispatch, movement__posted_on=dispatch.date, movement__quantity=dispatch.quantity,
    ).select_related("movement").first()
    if issue is None:
        raise ValidationError("Value the exact stock issue linked to this dispatch first.")

    ledgers = Ledger.objects.filter(workspace=workspace, group__workspace=workspace).select_related("group")
    asset = ledgers.filter(pk=inventory_ledger_id, group__kind=AccountGroup.Kind.ASSET).first()
    expense = ledgers.filter(pk=expense_ledger_id, group__kind=AccountGroup.Kind.EXPENSE).first()
    if asset is None or expense is None or asset.pk in invoice.ledger_ids.values():
        raise ValidationError("Choose a separate inventory asset and a cost-of-sales expense ledger in this company.")

    journal = None
    if not Period.objects.filter(year__workspace=workspace, starts_on__lte=invoice.posting_on,
                                 ends_before__gt=invoice.posting_on, locked_at__isnull=True).exists():
        raise ValidationError("The cost posting date needs an open period.")
    if issue.amount:
        if posted_asset_balance(workspace, asset, invoice.posting_on) < issue.amount:
            raise ValidationError("Post the reviewed acquisition cost to the inventory ledger before costing the sale.")
        journal = post_journal(
            workspace, actor, date=invoice.posting_on, kind=Journal.Kind.STOCK_COST,
            reference=f"COGS-{invoice.number}", narration="Cost of dispatched stock",
            submission_key=uuid5(NAMESPACE_URL, f"steel-quotes/cost-of-sale/{invoice.pk}"),
            lines=[(expense, "D", issue.amount), (asset, "C", issue.amount)], stock_workflow=True,
        )
    return SaleCost.objects.create(invoice=invoice, issue=issue, inventory_ledger=asset, expense_ledger=expense,
                                   journal=journal, recorded_by=actor)


@transaction.atomic
def restore_sale_cost(workspace, actor, *, movement_id, correction):
    """Restore the original issue value using a separate, confirmed stock receipt."""
    _check_enabled()
    lock_books(workspace, actor)
    invoice = correction.invoice
    cost = SaleCost.objects.filter(
        invoice=invoice, invoice__workspace=workspace, issue__movement__workspace=workspace,
    ).select_related("issue__movement", "inventory_ledger__group", "expense_ledger__group", "journal").first()
    if cost is None:
        raise ValidationError("This invoice has no recorded cost in your company.")
    is_return = isinstance(correction, InvoiceReturn)
    source = {"invoice_return": correction} if is_return else {"cancellation": correction}
    prior = cost.corrections.filter(**source).select_related("receipt").first()
    if prior:
        if prior.receipt.movement_id != movement_id:
            raise ValidationError("This correction already uses a different stock receipt.")
        return prior
    quantity = correction.quantity if is_return else cost.issue.movement.quantity
    document = correction.journal if is_return else correction.reversal
    if document.workspace_id != workspace.pk or not document.sealed:
        raise ValidationError("Choose a sealed invoice correction in this company.")
    receipt = unvalued_stock_correction(
        workspace, movement_id=movement_id, original=cost.issue.movement, kind=StockMovement.Kind.RECEIPT,
        posted_on=document.date, quantity=quantity,
    )
    if receipt is None:
        raise ValidationError("Choose the unvalued restock receipt for the same lot, quantity and correction date.")
    returned = sum((entry.receipt.movement.quantity for entry in cost.corrections.select_related("receipt__movement")),
                   Decimal(0))
    original_quantity = cost.issue.movement.quantity
    if returned + quantity > original_quantity:
        raise ValidationError("The correction exceeds the original costed dispatch quantity.")

    amount = rounded(cost.issue.amount * (returned + quantity) / original_quantity) - rounded(
        cost.issue.amount * returned / original_quantity,
    )
    valued = value_stock_movement(workspace, actor, movement_id=receipt.pk, material=amount)
    journal = None
    if amount:
        journal = post_journal(
            workspace, actor, date=document.date, kind=Journal.Kind.STOCK_RETURN,
            reference=f"STOCK-{document.reference}", narration="Restore returned stock at the original issue cost",
            submission_key=uuid5(NAMESPACE_URL, f"steel-quotes/restore-stock/{invoice.pk}/{document.pk}"),
            lines=[(cost.inventory_ledger, "D", amount), (cost.expense_ledger, "C", amount)],
            reverses=cost.journal if not is_return else None, stock_workflow=True,
        )
    return SaleCostCorrection.objects.create(sale_cost=cost, receipt=valued, journal=journal, recorded_by=actor, **source)
