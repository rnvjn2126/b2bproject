import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from django.core.exceptions import ValidationError
from django.db import transaction

from accounting.models import AccountGroup, Journal, JournalLine, Ledger
from accounting.services import lock_books, post_journal
from invoicing.tax import check_decimal

from .models import FundsAccount


def company_funds(workspace):
    return FundsAccount.objects.filter(
        workspace=workspace, ledger__workspace=workspace, ledger__group__workspace=workspace,
        ledger__group__kind=AccountGroup.Kind.ASSET,
    ).select_related("ledger__group")


@transaction.atomic
def register_funds_account(workspace, actor, *, ledger_id, name, kind, last_four=""):
    lock_books(workspace, actor)
    ledger = Ledger.objects.filter(
        workspace=workspace, group__workspace=workspace, group__kind=AccountGroup.Kind.ASSET, pk=ledger_id,
    ).first()
    if not ledger or kind not in FundsAccount.Kind.values:
        raise ValidationError("Choose an asset ledger and an account type in this workspace.")
    if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 100
            or not isinstance(last_four, str) or (last_four and (kind != FundsAccount.Kind.BANK
                                                                or not re.fullmatch(r"[0-9]{4}", last_four)))):
        raise ValidationError("Enter an account name and, for banks, at most the last four digits.")
    name = name.strip()
    existing = company_funds(workspace).filter(ledger=ledger).first()
    if existing:
        if (existing.name, existing.kind, existing.last_four) != (name, kind, last_four):
            raise ValidationError("This ledger already has a funds account.")
        return existing
    if company_funds(workspace).filter(name=name).exists():
        raise ValidationError("Use a distinct account name.")
    return FundsAccount.objects.create(workspace=workspace, ledger=ledger, name=name, kind=kind, last_four=last_four)


@transaction.atomic
def transfer_funds(workspace, actor, *, from_id, to_id, posting_on, amount, submission_key, reference=""):
    lock_books(workspace, actor)
    if from_id == to_id:
        raise ValidationError("Choose two different funds accounts.")
    accounts = company_funds(workspace).in_bulk([from_id, to_id])
    if len(accounts) != 2:
        raise ValidationError("Choose both funds accounts in this workspace.")
    check_decimal(amount, 15, 2)
    if amount <= 0 or type(posting_on) is not date or not isinstance(submission_key, UUID):
        raise ValidationError("Enter a positive transfer, posting date and submission key.")
    if not isinstance(reference, str) or len(reference.strip()) > 100:
        raise ValidationError("Enter a transfer reference of up to 100 characters.")
    return post_journal(
        workspace, actor, date=posting_on, kind=Journal.Kind.CONTRA, reference=reference.strip(),
        narration="Internal funds transfer",
        submission_key=uuid5(NAMESPACE_URL, f"steel-quotes/funds-transfer/{workspace.pk}/{submission_key}"),
        lines=((accounts[to_id].ledger, "D", amount), (accounts[from_id].ledger, "C", amount)),
    )


@dataclass(frozen=True)
class FundsBook:
    account: FundsAccount
    opening: Decimal
    rows: list
    closing: Decimal


def funds_book(workspace, *, account_id, start_on, end_on):
    if type(start_on) is not date or type(end_on) is not date or start_on > end_on:
        raise ValidationError("Choose a valid book date range.")
    account = company_funds(workspace).filter(pk=account_id).first()
    if not account:
        raise ValidationError("Choose a funds account in this workspace.")
    lines = JournalLine.objects.filter(
        journal__workspace=workspace, journal__sealed=True, journal__date__lte=end_on, ledger=account.ledger,
    ).select_related("journal").order_by("journal__date", "journal_id", "id")
    opening = balance = Decimal(0)
    rows = []
    for line in lines:
        movement = line.amount if line.side == "D" else -line.amount
        balance += movement
        if line.journal.date < start_on:
            opening = balance
        else:
            rows.append((line, balance))
    return FundsBook(account, opening, rows, balance)
