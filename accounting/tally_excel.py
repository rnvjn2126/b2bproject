from collections import defaultdict
from datetime import date, datetime, time
from io import BytesIO
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from defusedxml.common import DefusedXmlException
from django.core.exceptions import ValidationError
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from dashboard.workbook_security import inspect_xlsx_archive

from .tally_xml import MAX_BYTES, MAX_RECORDS, GroupRow, StockRow, amount, ledger_row, stock_unit, voucher_row


SHEET_COLUMNS = {
    "groups": {"name": "Name", "parent": "Parent"},
    "ledgers": {"name": "Name", "parent": "Parent", "opening": "Opening Balance",
                "email": "Email", "phone": "Phone", "address": "Address"},
    "stock items": {"name": "Name", "unit": "Base Units", "opening": "Opening Balance"},
    "vouchers": {"kind": "Voucher Type", "date": "Date", "number": "Voucher Number", "guid": "GUID",
                 "narration": "Narration", "ledger": "Ledger Name", "amount": "Amount", "debit": "Debit", "credit": "Credit"},
}
REQUIRED_COLUMNS = {"groups": {"name", "parent"}, "ledgers": {"name", "parent"},
                    "stock items": {"name", "unit"}, "vouchers": {"kind", "date", "number", "ledger"}}


def _text(value):
    return "" if value is None else str(value).strip()


def _day(value):
    if isinstance(value, datetime):
        if value.time() != time.min:
            raise ValidationError("Use a date without a time.")
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    text = _text(value)
    if "-" in text:
        try:
            return date.fromisoformat(text).strftime("%Y%m%d")
        except ValueError:
            raise ValidationError("Use a valid voucher date.") from None
    return text


def _values(cells):
    if len(cells) > 40:
        raise ValidationError("Use at most 40 workbook columns.")
    if any(cell.data_type in ("f", "e") for cell in cells):
        raise ValidationError("Formulas and spreadsheet errors cannot be imported.")
    return [cell.value for cell in cells]


def _indices(sheet, columns, heading):
    labels = [_text(cell).casefold() for cell in heading]
    used = [label for label in labels if label]
    if len(used) != len(set(used)):
        raise ValidationError("Use distinct workbook column headings.")
    indices = {field: labels.index(label.casefold()) for field, label in columns.items()
               if label.casefold() in labels}
    if len(indices) != len(set(indices.values())):
        raise ValidationError("Map each source column to one destination field.")
    if not REQUIRED_COLUMNS[sheet] <= indices.keys():
        missing = sorted(REQUIRED_COLUMNS[sheet] - indices.keys())
        raise ValidationError(f"Map the required workbook columns: {', '.join(missing)}.")
    if sheet == "vouchers":
        signed = "amount" in indices
        separate = {"debit", "credit"} <= indices.keys()
        if signed == separate or signed and {"debit", "credit"} & indices.keys():
            raise ValidationError("Use the signed Amount column or separate Debit and Credit columns.")
    return indices


def _master_row(sheet, row):
    if sheet == "groups":
        if not 1 <= len(row["name"]) <= 120 or not 1 <= len(row["parent"]) <= 120:
            raise ValidationError("Enter a group name and parent up to 120 characters.")
        return GroupRow(row["name"], row["parent"])
    if sheet == "ledgers":
        return ledger_row(row["name"], row["parent"], row["opening"], row["email"], row["phone"], row["address"])
    if not 1 <= len(row["name"]) <= 160 or (row["opening"] and amount(row["opening"]) != 0):
        raise ValidationError("Enter a stock name up to 160 characters with no opening quantity.")
    return StockRow(row["name"], stock_unit(row["unit"]))


def parse_tally_excel(content, mapping):
    if not isinstance(content, bytes) or not 0 < len(content) <= MAX_BYTES:
        raise ValidationError("Choose an XLSX workbook up to 512 KiB.")
    result, vouchers, seen = [], defaultdict(list), set()
    number_read = 0
    try:
        inspect_xlsx_archive(content)
        book = load_workbook(BytesIO(content), read_only=True, data_only=False, keep_links=False)
        try:
            if not 1 <= len(book.worksheets) <= len(SHEET_COLUMNS) or len(book.sheetnames) != len(book.worksheets):
                raise ValidationError("Use the supported master and voucher worksheets.")
            for sheet in book.worksheets:
                name = sheet.title.strip().casefold()
                if name not in SHEET_COLUMNS or name in seen or sheet.sheet_state != "visible":
                    raise ValidationError(f"Unsupported worksheet: {sheet.title}.")
                seen.add(name)
                sheet.reset_dimensions()
                cells = iter(sheet.iter_rows())
                columns = SHEET_COLUMNS[name] | mapping.get(name, {})
                indices = _indices(name, columns, _values(next(cells, ())))
                for number, cell_row in enumerate(cells, start=2):
                    number_read += 1
                    if number_read > MAX_RECORDS:
                        raise ValidationError("Use at most 500 data rows per workbook.")
                    try:
                        values = _values(cell_row)
                        if not any(value is not None for value in values):
                            continue
                        raw = {field: values[index] for field, index in indices.items() if index < len(values)}
                        row = {field: _text(raw.get(field)) for field in columns}
                        if name != "vouchers":
                            result.append(_master_row(name, row))
                            continue
                        ledger = row["ledger"]
                        if not 1 <= len(ledger) <= 120:
                            raise ValidationError("Enter a ledger name up to 120 characters.")
                        if "amount" in indices:
                            value = amount(row["amount"])
                        else:
                            debit, credit = amount(row["debit"] or "0"), amount(row["credit"] or "0")
                            if debit < 0 or credit < 0 or bool(debit) == bool(credit):
                                raise ValidationError("Enter a positive amount in just one debit or credit column.")
                            value = credit - debit
                        day = _day(raw.get("date"))
                        identity = row["guid"] or f"{row['kind'].casefold()}/{day}/{row['number']}"
                        key = identity.casefold()
                        metadata = (row["kind"], day, row["number"], row["guid"], row["narration"])
                        if vouchers[key] and vouchers[key][0] != metadata:
                            raise ValidationError("Voucher lines disagree on their date, type, number or narration.")
                        if not vouchers[key]:
                            vouchers[key].append(metadata)
                        vouchers[key].append((ledger, value))
                    except ValidationError as error:
                        raise ValidationError([f"{sheet.title} row {number}. {message}" for message in error.messages]) from None
        finally:
            book.close()
    except (BadZipFile, ParseError, DefusedXmlException, InvalidFileException, KeyError, ValueError, TypeError,
            IndexError, OSError):
        raise ValidationError("Choose a valid, supported XLSX workbook.") from None
    for source in vouchers.values():
        result.append(voucher_row(*source[0], source[1:]))
    if not result:
        raise ValidationError("There are no importable workbook rows.")
    return tuple(result)
