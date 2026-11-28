import csv
from datetime import date, datetime, time
from io import BytesIO, StringIO
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from defusedxml.common import DefusedXmlException
from django.core.exceptions import ValidationError
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from dashboard.workbook_security import inspect_xlsx_archive

from .statement_csv import MAX_STATEMENT_BYTES, MAX_STATEMENT_ROWS, STATEMENT_COLUMNS, parse_statement_csv


def _row_values(cells, number):
    if any(cell.data_type in ("f", "e") for cell in cells):
        raise ValidationError(f"Workbook row {number} contains a formula or spreadsheet error.")
    values = [cell.value for cell in cells]
    if not any(value is not None for value in values):
        return None
    if len(values) > len(STATEMENT_COLUMNS):
        raise ValidationError(f"Workbook row {number} has extra columns.")
    values.extend([None] * (len(STATEMENT_COLUMNS) - len(values)))
    if number == 1:
        return values
    day, reference, description, debit, credit = values
    if isinstance(day, datetime) and day.time() == time.min:
        day = day.date()
    if isinstance(day, date):
        day = day.isoformat()
    if any(value is not None and not isinstance(value, str) for value in (day, reference, description)):
        raise ValidationError(f"Workbook row {number} needs a date and text reference and description columns.")
    return day, reference, description, debit, credit


def parse_statement_excel(content):
    if not isinstance(content, bytes) or not 0 < len(content) <= MAX_STATEMENT_BYTES:
        raise ValidationError("Choose an XLSX workbook up to 256 KB.")
    try:
        inspect_xlsx_archive(content)
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=False, keep_links=False)
        try:
            if len(workbook.sheetnames) != 1 or len(workbook.worksheets) != 1:
                raise ValidationError("Use one worksheet for the bank statement.")
            sheet = workbook.worksheets[0]
            # Check the rows themselves even if the workbook reports a smaller used range.
            sheet.reset_dimensions()
            output = StringIO(newline="")
            writer = csv.writer(output)
            for number, cells in enumerate(sheet.iter_rows(), start=1):
                if number > MAX_STATEMENT_ROWS + 1:
                    raise ValidationError("Use at most 1,000 statement rows per workbook.")
                values = _row_values(cells, number)
                if values is not None:
                    writer.writerow(values)
                elif number == 1:
                    raise ValidationError("Put the statement column headings in the first worksheet row.")
        finally:
            workbook.close()
    except (BadZipFile, ParseError, DefusedXmlException, InvalidFileException, KeyError, ValueError, TypeError,
            IndexError, OSError) as error:
        raise ValidationError("Choose a valid, supported XLSX workbook.") from error
    return parse_statement_csv(output.getvalue().encode("utf-8"))
