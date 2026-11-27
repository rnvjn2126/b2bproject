from dataclasses import dataclass
from hashlib import sha256

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounting.services import lock_books

from .models import FundsAccount, StatementBatch, StatementLine
from .services import company_funds
from .statement_csv import StatementRow, parse_statement_csv


@dataclass(frozen=True)
class StatementPreview:
    digest: str
    new: list[StatementRow]
    duplicates: list[StatementRow]


def _statement_preview(account, content):
    rows = parse_statement_csv(content)
    if any(row.posted_on > timezone.localdate() for row in rows):
        raise ValidationError("Statement entries cannot be dated in the future.")
    seen = set(StatementLine.objects.filter(
        account=account, batch__account=account, fingerprint__in=[row.fingerprint for row in rows],
    ).values_list("fingerprint", flat=True))
    new, duplicates = [], []
    for row in rows:
        (duplicates if row.fingerprint in seen else new).append(row)
    digest = sha256(f"{account.pk}:".encode() + content).hexdigest()
    return StatementPreview(digest, new, duplicates)


def preview_statement(workspace, actor, *, account_id, content):
    if workspace.owner_id != actor.pk or not actor.is_active:
        raise PermissionDenied
    account = company_funds(workspace).filter(pk=account_id, kind=FundsAccount.Kind.BANK).first()
    if not account:
        raise ValidationError("Choose a bank account in this workspace.")
    return _statement_preview(account, content)


@transaction.atomic
def import_statement(workspace, actor, *, account_id, content, preview_digest, skip_known=False):
    """Stage confirmed statement entries independently of the accounting ledger."""
    lock_books(workspace, actor)
    account = company_funds(workspace).filter(pk=account_id, kind=FundsAccount.Kind.BANK).first()
    if not account:
        raise ValidationError("Choose a bank account in this workspace.")
    preview = _statement_preview(account, content)
    if preview.digest != preview_digest:
        raise ValidationError("The file changed after preview. Preview it again.")
    existing = StatementBatch.objects.filter(account=account, file_digest=preview.digest).first()
    if existing:
        return existing
    if preview.duplicates and skip_known is not True:
        raise ValidationError("The statement overlaps prior imports. Confirm skipping the known entries.")
    batch = StatementBatch.objects.create(
        account=account, file_digest=preview.digest, imported_rows=len(preview.new),
        duplicate_rows=len(preview.duplicates), imported_by=actor,
    )
    StatementLine.objects.bulk_create(
        StatementLine(account=account, batch=batch, posted_on=row.posted_on, reference=row.reference,
                      description=row.description, amount=row.amount, direction=row.direction,
                      fingerprint=row.fingerprint)
        for row in preview.new
    )
    return batch
