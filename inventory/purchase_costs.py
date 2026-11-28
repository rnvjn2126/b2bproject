from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounting.models import AccountGroup, Journal, JournalLine, Ledger
from accounting.services import lock_books, post_journal
from invoicing.models import InvoiceDraft, InvoiceReturn, IssuedInvoice
from invoicing.tax import rounded

from .models import PurchaseCost, PurchaseCostCorrection, StockMovement, ValuationEvent
from .stock import unvalued_stock_correction
from .valuation import value_stock_movement


@transaction.atomic
def capitalise_purchase_cost(workspace, actor, *, invoice_id, inventory_ledger_id):
    if not settings.INTERNAL_STOCK_ACCOUNTING:
        raise PermissionDenied("Internal stock accounting is disabled.")
    lock_books(workspace, actor)
    invoice = IssuedInvoice.objects.filter(
        pk=invoice_id, workspace=workspace, kind=InvoiceDraft.Kind.PURCHASE, draft__workspace=workspace,
        draft__movement__purchase_order__requirement__order__workspace=workspace, journal__workspace=workspace,
        journal__sealed=True, journal__kind=Journal.Kind.PURCHASE_INVOICE,
    ).select_related("draft__movement", "journal").first()
    if invoice is None or invoice.journal.date != invoice.posting_on:
        raise ValidationError("Choose an issued purchase invoice in this company.")
    existing = PurchaseCost.objects.filter(invoice=invoice).first()
    if existing:
        if existing.inventory_ledger_id != inventory_ledger_id:
            raise ValidationError("This invoice already uses a different inventory ledger.")
        return existing
    if hasattr(invoice, "cancellation") or invoice.returns.exists():
        raise ValidationError("Review existing invoice corrections before recording its acquisition cost.")
    asset = Ledger.objects.filter(pk=inventory_ledger_id, workspace=workspace, group__workspace=workspace,
                                 group__kind=AccountGroup.Kind.ASSET).select_related("group").first()
    source = JournalLine.objects.filter(
        journal=invoice.journal, ledger_id=invoice.ledger_ids.get("purchases"), side=JournalLine.Side.DEBIT,
        ledger__workspace=workspace, ledger__group__workspace=workspace,
        ledger__group__kind__in=[AccountGroup.Kind.ASSET, AccountGroup.Kind.EXPENSE],
    ).select_related("ledger__group").first()
    if asset is None or source is None or (asset.pk != source.ledger_id and asset.pk in invoice.ledger_ids.values()):
        raise ValidationError("Choose an inventory asset ledger and a sealed purchase cost line.")

    confirmed = invoice.draft.movement
    receipt = StockMovement.objects.filter(
        workspace=workspace, lot__workspace=workspace, lot__product__owner_id=workspace.owner_id,
        kind=StockMovement.Kind.RECEIPT, order_movement=confirmed, posted_on=confirmed.date, quantity=confirmed.quantity,
    ).first()
    if receipt is None:
        raise ValidationError("Record the exact stock receipt linked to this purchase invoice first.")
    valued = ValuationEvent.objects.filter(movement=receipt).first()
    if valued is None:
        valued = value_stock_movement(workspace, actor, movement_id=receipt.pk, material=source.amount)
    elif valued.amount != source.amount:
        raise ValidationError("The receipt value differs from the sealed acquisition amount. Review extra charges separately.")

    journal = None
    if asset.pk != source.ledger_id:
        journal = post_journal(
            workspace, actor, date=invoice.posting_on, kind=Journal.Kind.STOCK_ACQUISITION,
            reference=f"STOCK-{invoice.number}", narration="Capitalise the reviewed acquisition cost",
            submission_key=uuid5(NAMESPACE_URL, f"steel-quotes/stock-acquisition/{invoice.pk}"),
            lines=[(asset, "D", source.amount), (source.ledger, "C", source.amount)],
            stock_workflow=True,
        )
    return PurchaseCost.objects.create(
        invoice=invoice, receipt=valued, source_line=source, inventory_ledger=asset, journal=journal, recorded_by=actor,
    )


@transaction.atomic
def reverse_purchase_cost(workspace, actor, *, movement_id, correction):
    if not settings.INTERNAL_STOCK_ACCOUNTING:
        raise PermissionDenied("Internal stock accounting is disabled.")
    lock_books(workspace, actor)
    invoice = correction.invoice
    cost = PurchaseCost.objects.filter(
        invoice=invoice, invoice__workspace=workspace, receipt__movement__workspace=workspace,
    ).select_related("receipt__movement", "inventory_ledger__group", "source_line__ledger__group", "journal").first()
    if cost is None:
        raise ValidationError("This invoice has no recorded acquisition cost in your company.")
    is_return = isinstance(correction, InvoiceReturn)
    source = {"invoice_return": correction} if is_return else {"cancellation": correction}
    prior = cost.corrections.filter(**source).select_related("issue").first()
    if prior:
        if prior.issue.movement_id != movement_id:
            raise ValidationError("This correction already uses a different stock issue.")
        return prior

    original = cost.receipt.movement
    quantity = correction.quantity if is_return else original.quantity
    document = correction.journal if is_return else correction.reversal
    if document.workspace_id != workspace.pk or not document.sealed:
        raise ValidationError("Choose a sealed invoice correction in this company.")
    issue = unvalued_stock_correction(
        workspace, movement_id=movement_id, original=original, kind=StockMovement.Kind.ISSUE,
        posted_on=document.date, quantity=quantity,
    )
    if issue is None:
        raise ValidationError("Choose the unvalued stock issue for the same lot, quantity and correction date.")
    returned = sum((entry.issue.movement.quantity for entry in cost.corrections.select_related("issue__movement")),
                   Decimal(0))
    if returned + quantity > original.quantity:
        raise ValidationError("The correction exceeds the original receipt quantity.")
    total = cost.source_line.amount
    expected = rounded(total * (returned + quantity) / original.quantity) - rounded(total * returned / original.quantity)
    valued = value_stock_movement(workspace, actor, movement_id=issue.pk)
    if valued.amount != expected:
        raise ValidationError("The stock issue value differs from the purchase correction. Review the cost variance first.")

    journal = None
    if expected and cost.journal_id is not None:
        journal = post_journal(
            workspace, actor, date=document.date, kind=Journal.Kind.STOCK_RETURN,
            reference=f"STOCK-{document.reference}", narration="Release inventory cost on supplier return",
            submission_key=uuid5(NAMESPACE_URL, f"steel-quotes/reverse-acquisition/{invoice.pk}/{document.pk}"),
            lines=[(cost.source_line.ledger, "D", expected), (cost.inventory_ledger, "C", expected)],
            reverses=cost.journal if not is_return else None, stock_workflow=True,
        )
    return PurchaseCostCorrection.objects.create(purchase_cost=cost, issue=valued, journal=journal,
                                                recorded_by=actor, **source)
