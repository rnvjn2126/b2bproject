from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from accounting.models import JournalLine
from accounting.services import lock_books

from .models import FundsAccount, StatementLine, StatementMatch
from .services import company_funds


def _require_owner(workspace, actor):
    if workspace.owner_id != actor.pk or not actor.is_active:
        raise PermissionDenied


def _bank_accounts(workspace):
    return company_funds(workspace).filter(kind=FundsAccount.Kind.BANK)


def get_statement_entry(workspace, pk):
    line = StatementLine.objects.filter(
        pk=pk, account__in=_bank_accounts(workspace), batch__account_id=F("account_id"),
    ).select_related("account").first()
    if line is None:
        raise ValidationError("Choose a staged statement entry in this workspace.")
    return line


def _bank_lines(account):
    return JournalLine.objects.filter(
        ledger_id=account.ledger_id, journal__workspace_id=account.workspace_id, journal__sealed=True,
    )


def _matching_lines(statement):
    return _bank_lines(statement.account).filter(side="D" if statement.direction == "in" else "C",
                                                 amount=statement.amount)


def suggest_matches(workspace, actor, *, statement_line_id):
    _require_owner(workspace, actor)
    statement = get_statement_entry(workspace, statement_line_id)
    if hasattr(statement, "match"):
        return []
    day = statement.posted_on.toordinal()
    candidates = _matching_lines(statement).filter(
        bank_match__isnull=True, journal__date__gte=date.fromordinal(max(1, day - 7)),
        journal__date__lte=date.fromordinal(min(date.max.toordinal(), day + 7)),
    ).select_related("journal", "reportedinstrument")

    def rank(line):
        instrument = getattr(line, "reportedinstrument", None)
        references = [line.journal.reference.strip().upper()]
        if instrument and instrument.account_id == statement.account_id:
            references.append(instrument.reference)
        return (not (statement.reference and statement.reference in references),
                abs((line.journal.date - statement.posted_on).days), line.pk)

    return sorted(candidates, key=rank)[:20]


@transaction.atomic
def confirm_match(workspace, actor, *, statement_line_id, journal_line_id):
    """Confirm a one-to-one ledger comparison without posting a journal."""
    lock_books(workspace, actor)
    statement = get_statement_entry(workspace, statement_line_id)
    previous = StatementMatch.objects.filter(statement_line=statement).first()
    if previous:
        if previous.journal_line_id != journal_line_id:
            raise ValidationError("This statement entry is already reconciled.")
        return previous
    journal_line = _matching_lines(statement).filter(pk=journal_line_id).first()
    if not journal_line:
        raise ValidationError("Choose a sealed bank line with the same account, amount and direction.")
    if StatementMatch.objects.filter(journal_line=journal_line).exists():
        raise ValidationError("This journal line is already reconciled.")
    return StatementMatch.objects.create(statement_line=statement, journal_line=journal_line, confirmed_by=actor)


@dataclass(frozen=True)
class UnmatchedReport:
    statements: list[StatementLine]
    journal_lines: list[JournalLine]
    statement_net: Decimal
    ledger_net: Decimal

    @property
    def difference(self):
        return self.statement_net - self.ledger_net


def unmatched_report(workspace, actor, *, account_id, start_on, end_on):
    _require_owner(workspace, actor)
    if (type(start_on) is not date or type(end_on) is not date
            or not start_on <= end_on <= timezone.localdate()):
        raise ValidationError("Choose a valid date range ending on or before today.")
    account = _bank_accounts(workspace).filter(pk=account_id).first()
    if not account:
        raise ValidationError("Choose a bank account in this workspace.")
    statements = list(StatementLine.objects.filter(
        account=account, batch__account=account, match__isnull=True, posted_on__range=(start_on, end_on),
    ).order_by("posted_on", "pk"))
    journal_lines = list(_bank_lines(account).filter(
        bank_match__isnull=True, journal__date__range=(start_on, end_on),
    ).select_related("journal").order_by("journal__date", "pk"))
    statement_net = sum((line.amount if line.direction == "in" else -line.amount for line in statements), Decimal(0))
    ledger_net = sum((line.amount if line.side == "D" else -line.amount for line in journal_lines), Decimal(0))
    return UnmatchedReport(statements, journal_lines, statement_net, ledger_net)
