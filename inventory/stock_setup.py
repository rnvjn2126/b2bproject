import re
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256

from django.core.exceptions import ValidationError
from django.db import transaction

from accounting.services import lock_books
from dashboard.models import Product

from .models import LotCertificate, SteelSpecification, StockLot, StorageLocation, Warehouse


MAX_CERTIFICATE_BYTES = 512 * 1024


def _code(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{0,23}", value.strip().upper()):
        raise ValidationError("Enter a code up to 24 characters using letters, digits and hyphens.")
    return value.strip().upper()


def _required_name(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 100:
        raise ValidationError("Enter a name up to 100 characters.")
    return value.strip()


@transaction.atomic
def register_warehouse(workspace, actor, *, code, name):
    lock_books(workspace, actor)
    name = _required_name(name)
    warehouse, _ = Warehouse.objects.get_or_create(workspace=workspace, code=_code(code), defaults={"name": name})
    if warehouse.name != name:
        raise ValidationError("This warehouse code already has a different name.")
    return warehouse


@transaction.atomic
def register_location(workspace, actor, *, warehouse_id, code, name):
    lock_books(workspace, actor)
    warehouse = Warehouse.objects.filter(workspace=workspace, pk=warehouse_id).first()
    if warehouse is None:
        raise ValidationError("Choose a warehouse in this company.")
    name = _required_name(name)
    location, _ = StorageLocation.objects.get_or_create(warehouse=warehouse, code=_code(code), defaults={"name": name})
    if location.name != name:
        raise ValidationError("This warehouse already uses that location code.")
    return location


@transaction.atomic
def register_lot(workspace, actor, *, code, product_id, heat_number="", batch_number="", mill_name="",
                 manufacturer_name=""):
    lock_books(workspace, actor)
    product = Product.objects.filter(pk=product_id, owner_id=workspace.owner_id).first()
    if product is None or product.unit not in Product.Unit.values:
        raise ValidationError("Choose a catalogue product with a supported stock unit in this company.")
    identifiers = (heat_number, batch_number, mill_name, manufacturer_name)
    if any(not isinstance(value, str) or len(value.strip()) > 100 for value in identifiers):
        raise ValidationError("Keep heat, batch, mill and manufacturer details to 100 characters each.")
    identifiers = tuple(value.strip() for value in identifiers)
    code = _code(code)
    existing = StockLot.objects.filter(workspace=workspace, code=code).first()
    if existing:
        if (existing.product_id, existing.heat_number, existing.batch_number, existing.mill_name,
            existing.manufacturer_name) != (
            product.pk, *identifiers,
        ):
            raise ValidationError("This lot code is already assigned to different stock.")
        return existing

    specification = SteelSpecification.objects.filter(workspace=workspace, product=product).first()
    nominal = specification.theoretical_kg_per_m if specification else None
    if nominal is not None:
        nominal = nominal.quantize(Decimal("0.000000001"), rounding=ROUND_HALF_UP)
    lot = StockLot(
        workspace=workspace, code=code, product=product, unit=product.unit,
        grade=specification.grade if specification else product.grade,
        nominal_kg_per_m=nominal, length_mm=specification.length_mm if specification else None,
        heat_number=identifiers[0], batch_number=identifiers[1], mill_name=identifiers[2], manufacturer_name=identifiers[3],
    )
    lot.full_clean()
    lot.save()
    return lot


@transaction.atomic
def attach_lot_certificate(workspace, actor, *, lot_id, content):
    lock_books(workspace, actor)
    lot = StockLot.objects.filter(workspace=workspace, pk=lot_id, product__owner_id=workspace.owner_id).first()
    if lot is None:
        raise ValidationError("Choose a lot in this company.")
    if (not isinstance(content, bytes) or not 0 < len(content) <= MAX_CERTIFICATE_BYTES
            or not content.startswith(b"%PDF-") or not content.rstrip().endswith(b"%%EOF")):
        raise ValidationError("Choose a PDF certificate up to 512 KB.")
    digest = sha256(content).hexdigest()
    previous = LotCertificate.objects.filter(lot=lot).first()
    if previous:
        if previous.digest != digest:
            raise ValidationError("This lot already has a different certificate.")
        return previous
    return LotCertificate.objects.create(lot=lot, content=content, digest=digest, uploaded_by=actor)
