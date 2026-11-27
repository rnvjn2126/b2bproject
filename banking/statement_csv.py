import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError


STATEMENT_COLUMNS = ["date", "reference", "description", "debit", "credit"]
MAX_STATEMENT_BYTES = 256 * 1024
MAX_STATEMENT_ROWS = 1000


@dataclass(frozen=True)
class StatementRow:
    posted_on: date
    reference: str
    description: str
    amount: Decimal
    direction: str
    fingerprint: str


def amount_or_zero(value):
    if not value:
        return Decimal(0)
    if not re.fullmatch(r"[0-9]{1,13}(?:\.[0-9]{1,2})?", value):
        raise ValueError("Enter a nonnegative amount in rupees with up to two decimal places.")
    return Decimal(value)


def parse_statement_csv(content):
    if not isinstance(content, bytes) or not 0 < len(content) <= MAX_STATEMENT_BYTES:
        raise ValidationError("Choose a UTF-8 CSV file up to 256 KB.")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValidationError("Choose a UTF-8 CSV file.") from error
    if "\x00" in decoded:
        raise ValidationError("The statement contains binary data.")
    reader = csv.reader(StringIO(decoded, newline=""), strict=True)
    rows, fingerprints = [], set()
    try:
        if next(reader, []) != STATEMENT_COLUMNS:
            raise ValidationError("Use the columns date, reference, description, debit and credit in that order.")
        for raw in reader:
            line = reader.line_num
            if not raw or not any(cell.strip() for cell in raw):
                continue
            if len(rows) >= MAX_STATEMENT_ROWS:
                raise ValidationError("Use at most 1,000 statement rows per file.")
            try:
                day, ref, description, debit, credit = (field.strip() for field in raw)
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day):
                    raise ValueError("Use YYYY-MM-DD for the date.")
                posted_on = date.fromisoformat(day)
                if len(ref.upper()) > 80 or len(description) > 250:
                    raise ValueError("The reference or description is too long.")
                debit, credit = amount_or_zero(debit), amount_or_zero(credit)
                if bool(debit) == bool(credit):
                    raise ValueError("Enter a positive debit or credit in one column.")
            except ValueError as error:
                message = str(error) if len(raw) == 5 else "Enter all five columns."
                raise ValidationError(f"CSV line {line}: {message}") from error
            amount = debit or credit
            direction = "out" if debit else "in"
            ref = ref.upper()
            # With no bank reference, include the description to identify possible overlap.
            identity = [posted_on.isoformat(), ref, "" if ref else description, direction, f"{amount:.2f}"]
            fingerprint = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
            if fingerprint in fingerprints:
                raise ValidationError(f"CSV line {line}: repeated statement entry. Review duplicate source rows.")
            fingerprints.add(fingerprint)
            rows.append(StatementRow(posted_on, ref, description, amount, direction, fingerprint))
    except csv.Error as error:
        raise ValidationError(f"Invalid CSV near line {reader.line_num}.") from error
    if not rows:
        raise ValidationError("The CSV contains no statement entries.")
    return rows
