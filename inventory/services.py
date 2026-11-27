from django.core.exceptions import ValidationError
from django.db import transaction

from accounting.services import lock_books
from dashboard.models import Product

from .models import SteelSpecification


@transaction.atomic
def save_specification(workspace, actor, *, product_id, profile, grade, density_kg_m3, length_mm=None, diameter_mm=None,
                       width_mm=None, depth_mm=None, thickness_mm=None, flange_mm=None):
    lock_books(workspace, actor)
    product = Product.objects.filter(owner_id=workspace.owner_id, pk=product_id).first()
    if not product:
        raise ValidationError("Choose a product in this company.")
    specification = SteelSpecification.objects.filter(workspace=workspace, product=product).first()
    if specification is None:
        specification = SteelSpecification(workspace=workspace, product=product)
    specification.profile = profile
    specification.grade = (grade or product.grade).strip()
    specification.density_kg_m3 = density_kg_m3
    specification.length_mm = length_mm
    specification.diameter_mm = diameter_mm
    specification.width_mm = width_mm
    specification.depth_mm = depth_mm
    specification.thickness_mm = thickness_mm
    specification.flange_mm = flange_mm
    specification.full_clean()
    specification.save()
    return specification
