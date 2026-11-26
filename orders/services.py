from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import DecimalValidator
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from dashboard.accounts import can_manage_account
from dashboard.billing import user_has_seat
from dashboard.models import BusinessAccount, Quote, SupplierOffer

from .models import OrderMovement, PurchaseOrder, SalesOrder, SalesOrderLine


def lock_orders(workspace, actor):
    if not workspace or not can_manage_account(actor, workspace) or not user_has_seat(actor, workspace):
        raise PermissionDenied
    # Lock the shared company row before checking repeat conversion or state changes.
    BusinessAccount.objects.filter(pk=workspace.pk).update(name=F("name"))


@transaction.atomic
def convert_quote(workspace, actor, quote_id, customer_reference, delivery_on):
    lock_orders(workspace, actor)
    quote = Quote.objects.select_for_update().filter(pk=quote_id, owner_id=workspace.owner_id).first()
    if not quote or quote.rfq.owner_id != workspace.owner_id or quote.rfq.customer.owner_id != workspace.owner_id:
        raise ValidationError("The quotation is unavailable in this workspace.")
    if quote.status != Quote.Status.ACCEPTED or not quote.sent_at or not quote.closed_at:
        raise ValidationError("Convert a quotation with a recorded acceptance.")
    if not quote.number:
        raise ValidationError("The accepted quotation needs a quotation number before conversion.")
    previous = SalesOrder.objects.filter(workspace=workspace, quotation_number=quote.number).first()
    if previous:
        if previous.source_quote_id != quote.pk:
            raise ValidationError("Another revision of this quotation already has a sales order.")
        return previous

    lines = list(quote.lines.select_related("rfq_line__product", "supplier_offer__supplier"))
    if not lines or any(line.owner_id != workspace.owner_id for line in lines):
        raise ValidationError("The quotation needs valid items in this workspace.")
    for line in lines:
        # Reuse the quotation's existing scope and quantity rules before copying terms.
        line.full_clean(validate_unique=False, validate_constraints=False)
    if any(line.needs_review for line in lines) and not (quote.approved_by_id and quote.approved_at):
        raise ValidationError("The quotation requires gross-margin approval.")

    customer = quote.rfq.customer
    order = SalesOrder.objects.create(
        workspace=workspace, source_quote=quote, quotation_number=quote.number, quotation_revision=quote.revision,
        customer=customer, customer_name=customer.company_name or customer.name, customer_address=customer.billing_address,
        customer_reference=customer_reference, delivery_on=delivery_on, payment_terms=quote.payment_terms,
        delivery_terms=quote.delivery_terms, created_by=actor,
    )
    for line in lines:
        item = line.rfq_line
        product = item.product
        SalesOrderLine.objects.create(
            order=order, quote_line=line, description=item.description or (product.name if product else "Requested item"),
            grade=item.grade or (product.grade if product else ""), dimensions=item.dimensions or (product.dimensions if product else ""),
            quantity=line.quantity, unit=line.unit, unit_price=line.selling_price_per_unit,
        )
    return order


@transaction.atomic
def change_sales_status(workspace, actor, order_id, target, reason=""):
    lock_orders(workspace, actor)
    order = SalesOrder.objects.filter(workspace=workspace, pk=order_id).first()
    if not order:
        raise ValidationError("The sales order is unavailable in this workspace.")
    if target == order.status:
        return order
    if target == SalesOrder.Status.APPROVED and order.status == SalesOrder.Status.DRAFT:
        order.status = target
        order.approved_by = actor
        order.approved_at = timezone.now()
        order.save(update_fields=["status", "approved_by", "approved_at"])
    elif target == SalesOrder.Status.CANCELLED and order.status in (SalesOrder.Status.DRAFT, SalesOrder.Status.APPROVED):
        if order.lines.filter(dispatches__isnull=False).exists() or PurchaseOrder.objects.filter(
            requirement__order=order,
        ).exclude(status=SalesOrder.Status.CANCELLED).exists():
            raise ValidationError("Cancel open purchase orders first. Sales orders with dispatches cannot be cancelled.")
        if not reason.strip():
            raise ValidationError("Enter a cancellation reason.")
        order.status = target
        order.cancelled_by = actor
        order.cancelled_at = timezone.now()
        order.cancellation_reason = reason
        order.save(update_fields=["status", "cancelled_by", "cancelled_at", "cancellation_reason"])
    else:
        raise ValidationError("This sales order cannot move to that status.")
    return order


def total_quantity(records):
    return sum((quantity for quantity in records.values_list("quantity", flat=True).iterator()), Decimal(0))


def check_quantity(quantity):
    if not isinstance(quantity, Decimal) or not quantity.is_finite() or quantity <= 0:
        raise ValidationError("Enter a positive quantity.")
    DecimalValidator(14, 3)(quantity)


@transaction.atomic
def create_purchase(workspace, actor, line_id, offer_id, *, quantity, delivery_on, supplier_reference, submission_key):
    lock_orders(workspace, actor)
    check_quantity(quantity)
    line = SalesOrderLine.objects.filter(pk=line_id, order__workspace=workspace).select_related("order", "quote_line").first()
    if not line:
        raise ValidationError("The sales requirement is unavailable.")
    existing = line.purchases.filter(submission_key=submission_key).first()
    if existing:
        if (existing.offer_id, existing.quantity, existing.delivery_on, existing.supplier_reference) != (
            offer_id, quantity, delivery_on, supplier_reference,
        ):
            raise ValidationError("This submission key already belongs to another purchase order.")
        return existing
    if line.order.status != SalesOrder.Status.APPROVED:
        raise ValidationError("Approve the sales order before allocating purchases.")
    offer = SupplierOffer.objects.filter(
        pk=offer_id, owner_id=workspace.owner_id, supplier__owner_id=workspace.owner_id,
        rfq_line_id=line.quote_line.rfq_line_id, rfq_line__owner_id=workspace.owner_id,
    ).select_related("supplier", "rfq_line__product").first()
    if not offer or offer.rfq_line.unit != line.unit or offer.converted_available_quantity is None:
        raise ValidationError("Choose a compatible offer from this enquiry item.")
    active = line.purchases.exclude(status=SalesOrder.Status.CANCELLED)
    if quantity + total_quantity(active) > line.quantity:
        raise ValidationError("This would exceed the sales requirement.")
    if quantity + total_quantity(active.filter(offer=offer)) > offer.converted_available_quantity:
        raise ValidationError("This would exceed the supplier offer's available quantity.")
    unit_price = offer.normalized_unit_price.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    DecimalValidator(14, 4)(unit_price)
    if unit_price <= 0:
        raise ValidationError("The normalized rate is too small to record in the requested unit.")
    supplier = offer.supplier
    return PurchaseOrder.objects.create(
        requirement=line, offer=offer, supplier=supplier, supplier_name=supplier.company_name or supplier.name,
        supplier_reference=supplier_reference, delivery_on=delivery_on, quantity=quantity,
        unit_price=unit_price, submission_key=submission_key, created_by=actor,
    )


@transaction.atomic
def change_purchase_status(workspace, actor, purchase_id, target, reason=""):
    lock_orders(workspace, actor)
    purchase = PurchaseOrder.objects.filter(pk=purchase_id, requirement__order__workspace=workspace).first()
    if not purchase:
        raise ValidationError("The purchase order is unavailable.")
    if target == purchase.status:
        return purchase
    if target == SalesOrder.Status.APPROVED and purchase.status == SalesOrder.Status.DRAFT:
        purchase.approved_by, purchase.approved_at = actor, timezone.now()
        fields = ["approved_by", "approved_at"]
    elif target == SalesOrder.Status.CANCELLED and purchase.status in (SalesOrder.Status.DRAFT, SalesOrder.Status.APPROVED):
        if purchase.receipts.exists() or not reason.strip():
            raise ValidationError("Enter a cancellation reason. Purchase orders with receipts cannot be cancelled.")
        purchase.cancelled_by, purchase.cancelled_at, purchase.cancellation_reason = actor, timezone.now(), reason
        fields = ["cancelled_by", "cancelled_at", "cancellation_reason"]
    else:
        raise ValidationError("This purchase order cannot move to that status.")
    purchase.status = target
    purchase.save(update_fields=["status", *fields])
    return purchase


@transaction.atomic
def record_movement(workspace, actor, *, source_id, receipt, date, reference, quantity):
    lock_orders(workspace, actor)
    check_quantity(quantity)
    if not reference.strip() or date > timezone.localdate():
        raise ValidationError("Enter a document reference and a date no later than today.")
    if receipt:
        source = PurchaseOrder.objects.filter(pk=source_id, requirement__order__workspace=workspace).first()
        if not source or source.status != SalesOrder.Status.APPROVED:
            raise ValidationError("Choose an approved purchase order.")
        movements = source.receipts
        limit = source.quantity
    else:
        source = SalesOrderLine.objects.filter(pk=source_id, order__workspace=workspace).select_related("order").first()
        if not source or source.order.status != SalesOrder.Status.APPROVED:
            raise ValidationError("Choose an approved sales order item.")
        movements = source.dispatches
        received = OrderMovement.objects.filter(
            purchase_order__requirement=source, date__lte=date,
        )
        limit = min(source.quantity, total_quantity(received))
    existing = movements.filter(reference=reference).first()
    if existing:
        if (existing.date, existing.quantity) != (date, quantity):
            raise ValidationError("This document reference already has a different movement.")
        return existing
    if quantity + total_quantity(movements) > limit:
        raise ValidationError("The movement would exceed the outstanding or received quantity.")
    return movements.create(date=date, reference=reference, quantity=quantity, recorded_by=actor)
