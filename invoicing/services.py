from dataclasses import asdict
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounting.services import lock_books
from orders.models import OrderMovement, SalesOrder

from .models import CompanyGSTRegistration, InvoiceDraft, TaxRate
from .tax import calculate_line, invoice_total, validate_gstin


def eligible_movements(workspace):
    if workspace is None:
        return OrderMovement.objects.none()
    approved = SalesOrder.Status.APPROVED
    return OrderMovement.objects.filter(
        Q(sales_line__order__workspace=workspace, sales_line__order__status=approved,
          sales_line__order__customer__owner_id=workspace.owner_id)
        | Q(purchase_order__requirement__order__workspace=workspace,
            purchase_order__requirement__order__status=approved, purchase_order__status=approved,
            purchase_order__supplier__owner_id=workspace.owner_id),
    ).select_related("sales_line__order", "purchase_order__requirement", "purchase_order__supplier")


@transaction.atomic
def prepare_draft(workspace, actor, *, movement_id, registration_id, party_gstin, item_code,
                  place_of_supply, local_component, inclusive, discount, freight, round_off,
                  purchase_unit_price=None, supplier_invoice_date=None):
    """Snapshot a domestic goods estimate for one movement. The draft has no accounting effect."""
    lock_books(workspace, actor)
    if not isinstance(inclusive, bool):
        raise ValidationError("Choose tax-inclusive or tax-exclusive pricing.")
    movement = eligible_movements(workspace).filter(pk=movement_id).first()
    registration = CompanyGSTRegistration.objects.filter(workspace=workspace, pk=registration_id).first()
    if not movement or not registration:
        raise ValidationError("Choose a confirmed movement and GST registration in this workspace.")
    if InvoiceDraft.objects.filter(movement=movement).exists():
        raise ValidationError("This movement already has an internal invoice draft.")

    validate_gstin(registration.gstin)
    validate_gstin(party_gstin)
    has_supplier_actuals = purchase_unit_price is not None or supplier_invoice_date is not None
    if has_supplier_actuals and (movement.sales_line_id or purchase_unit_price is None
                                 or type(supplier_invoice_date) is not date
                                 or supplier_invoice_date > timezone.localdate()):
        raise ValidationError("Enter both actual supplier price and a valid supplier invoice date for a receipt.")
    rate_date = supplier_invoice_date if has_supplier_actuals else movement.date
    rate = TaxRate.effective_for(workspace, TaxRate.ItemKind.GOODS, item_code, rate_date)
    if not rate:
        raise ValidationError("Configure an HSN rate effective on the selected tax date.")
    if movement.sales_line_id:
        line = movement.sales_line
        kind = InvoiceDraft.Kind.SALES
        party_name, party_address = line.order.customer_name, line.order.customer_address
        supplier_state, unit_price = registration.gstin[:2], line.unit_price
    else:
        purchase = movement.purchase_order
        line = purchase.requirement
        kind = InvoiceDraft.Kind.PURCHASE
        party_name, party_address = purchase.supplier_name, purchase.supplier.address
        supplier_state = party_gstin[:2]
        unit_price = purchase_unit_price if has_supplier_actuals else purchase.unit_price
    if not all(value.strip() for value in (party_name, party_address, registration.registered_name,
                                           registration.registered_address)):
        raise ValidationError("The company and trading party need registered names and addresses.")

    tax = calculate_line(quantity=movement.quantity, unit_price=unit_price, discount=discount, freight=freight,
                         inclusive=inclusive, rate=rate, supplier_state=supplier_state,
                         place_of_supply=place_of_supply, local_component=local_component)
    total = invoice_total([tax], round_off)
    return InvoiceDraft.objects.create(
        workspace=workspace, movement=movement, registration=registration, rate=rate, kind=kind,
        supply_on=movement.date, total=total, created_by=actor,
        snapshot={
            "company": {"gstin": registration.gstin, "name": registration.registered_name,
                        "address": registration.registered_address},
            "party": {"gstin": party_gstin, "name": party_name, "address": party_address},
            "movement_reference": movement.reference,
            "tax_rate_date": rate_date.isoformat(),
            "supplier_invoice_date": supplier_invoice_date.isoformat() if has_supplier_actuals else None,
            "item": {"description": line.description, "grade": line.grade, "dimensions": line.dimensions,
                     "unit": line.unit, "quantity": str(movement.quantity), "unit_price": str(unit_price)},
            "rate": {"hsn": rate.item_code, "effective_from": rate.effective_from.isoformat(),
                     "source": rate.source_url, "integrated": str(rate.integrated_rate), "central": str(rate.central_rate),
                     "local": str(rate.local_rate), "cess": str(rate.cess_rate)},
            "place_of_supply": place_of_supply, "local_component": local_component, "inclusive": inclusive,
            "discount": str(discount), "freight": str(freight), "round_off": str(round_off),
            "tax": {component: str(amount) for component, amount in asdict(tax).items()},
        },
    )
