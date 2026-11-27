from datetime import date
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounting.models import JournalLine
from accounting.services import lock_books
from invoicing.tax import check_decimal

from .models import ChequeEvent, FundsAccount, ReportedInstrument
from .services import company_funds


@transaction.atomic
def record_instrument(workspace, actor, *, account_id, method, direction, reference, amount,
                      reported_on, journal_line_id=None):
    """Store a staff-entered reference independently of any verification process."""
    lock_books(workspace, actor)
    account = company_funds(workspace).filter(pk=account_id, kind=FundsAccount.Kind.BANK).first()
    if not account or method not in ReportedInstrument.Method.values or direction not in ReportedInstrument.Direction.values:
        raise ValidationError("Choose a bank account, payment method and direction.")
    check_decimal(amount, 15, 2)
    if amount <= 0 or type(reported_on) is not date or reported_on > timezone.localdate():
        raise ValidationError("Choose a positive amount and a reported date on or before today.")
    if not isinstance(reference, str) or not 1 <= len(reference.strip().upper()) <= 80:
        raise ValidationError("Enter a payment reference of up to 80 characters.")
    reference = reference.strip().upper()
    instrument = ReportedInstrument.objects.filter(account=account, method=method, direction=direction, reference=reference)
    previous = instrument.first()
    if previous:
        if (previous.amount, previous.reported_on, previous.journal_line_id) != (amount, reported_on, journal_line_id):
            raise ValidationError("This reported reference is already recorded with different details.")
        return previous

    if journal_line_id is not None:
        side = "D" if direction == ReportedInstrument.Direction.INFLOW else "C"
        if not JournalLine.objects.filter(pk=journal_line_id, journal__workspace=workspace, journal__sealed=True,
                                          ledger=account.ledger, side=side, amount=amount).exists():
            raise ValidationError("The posted bank line must match the account, amount and direction.")
        if ReportedInstrument.objects.filter(journal_line_id=journal_line_id).exists():
            raise ValidationError("This posted bank line already has a recorded instrument.")
    return ReportedInstrument.objects.create(
        account=account, journal_line_id=journal_line_id, method=method, direction=direction,
        reference=reference, amount=amount, reported_on=reported_on, recorded_by=actor,
    )


@transaction.atomic
def record_cheque_event(workspace, actor, *, instrument_id, state, happened_on, submission_key, reason=""):
    lock_books(workspace, actor)
    cheque = ReportedInstrument.objects.filter(
        account__in=company_funds(workspace), pk=instrument_id, method=ReportedInstrument.Method.CHEQUE,
    ).first()
    states = ChequeEvent.State
    if not cheque or state not in states.values or not isinstance(submission_key, UUID):
        raise ValidationError("Choose a cheque, event type and submission key.")
    if (not isinstance(reason, str) or len(reason.strip()) > 250
            or (state == states.RETURNED and not reason.strip())):
        raise ValidationError("Enter the return reason or a note of up to 250 characters.")
    reason = reason.strip()
    previous = cheque.cheque_events.filter(submission_key=submission_key).first()
    if previous:
        if (previous.state, previous.happened_on, previous.reason) != (state, happened_on, reason):
            raise ValidationError("This submission key already belongs to a different cheque event.")
        return previous
    latest = cheque.cheque_events.last()
    since = latest.happened_on if latest else cheque.reported_on
    if type(happened_on) is not date or not since <= happened_on <= timezone.localdate():
        raise ValidationError("The cheque event date cannot precede the last event or be in the future.")
    transitions = {
        None: (states.PRESENTED, states.RETURNED),
        states.PRESENTED: (states.CLEARED, states.RETURNED),
        states.CLEARED: (states.RETURNED,),
        states.RETURNED: (),
    }
    if state not in transitions[latest.state if latest else None]:
        raise ValidationError("This cheque event does not follow the recorded status.")
    return ChequeEvent.objects.create(
        instrument=cheque, state=state, happened_on=happened_on, reason=reason,
        submission_key=submission_key, recorded_by=actor,
    )
