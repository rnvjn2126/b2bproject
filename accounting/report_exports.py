import csv
from datetime import date
from decimal import Decimal
from io import BytesIO, StringIO
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from dashboard.csv_exports import safe_csv_cell

from .templatetags.indian_finance import inr


CONTENT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}
ROW_LIMITS = {"csv": 10_000, "xlsx": 5_000, "pdf": 600}
BLUE = "#162E54"


def _text(value):
    return ILLEGAL_CHARACTERS_RE.sub("", str(value)) if value is not None else ""


def _csv(table):
    result = StringIO()
    writer = csv.writer(result)
    writer.writerow(table.columns)
    for row in table.rows:
        writer.writerow(safe_csv_cell(_text(value)) if isinstance(value, str) else value for value in row)
    return result.getvalue().encode("utf-8-sig")


def _workbook(table, start, end):
    book = Workbook()
    sheet = book.active
    sheet.title = table.title[:31]
    sheet.append([table.title])
    sheet.append(["From", start, "Through", end])
    sheet.append(list(table.columns))
    sheet.freeze_panes = "A4"
    sheet["A1"].font = Font(size=14, bold=True, color=BLUE[1:])
    for cell in sheet[3]:
        cell.fill = PatternFill("solid", fgColor=BLUE[1:])
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(wrap_text=True)
    sheet.row_dimensions[3].height = 32
    widths = [max(12, min(38, len(title) + 5)) for title in table.columns]
    for index, row in enumerate(table.rows, start=4):
        for col, value in enumerate(row, start=1):
            if isinstance(value, str):
                content = _text(value)
                cell = sheet.cell(index, col, content)
                cell.data_type = "s"
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                widths[col - 1] = min(38, max(widths[col - 1], len(content) + 3))
            elif isinstance(value, Decimal):
                # Preserve amounts beyond Excel's 15 significant digits as exact text.
                if len(value.normalize().as_tuple().digits) > 15:
                    cell = sheet.cell(index, col, format(value, "f"))
                else:
                    cell = sheet.cell(index, col, value)
                    if "(INR)" in table.columns[col - 1]:
                        cell.number_format = "0.00"
            elif value is not None:
                cell = sheet.cell(index, col, value)
                if isinstance(value, date):
                    cell.number_format = "yyyy-mm-dd"
    for column, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(column)].width = width
    for column in ("B", "D"):
        sheet.column_dimensions[column].width = max(sheet.column_dimensions[column].width, 14)
    sheet.auto_filter.ref = f"A3:{get_column_letter(len(table.columns))}{max(3, sheet.max_row)}"
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def _pdf(table, start, end):
    output = BytesIO()
    page = landscape(A4)
    document = SimpleDocTemplate(output, pagesize=page, leftMargin=27, rightMargin=27, topMargin=28, bottomMargin=30)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportCell", fontSize=8, leading=10, wordWrap="CJK", textColor=colors.HexColor("#14243F")))
    styles.add(ParagraphStyle(name="ReportHead", parent=styles["ReportCell"], fontName="Helvetica-Bold", textColor=colors.white))
    styles.add(ParagraphStyle(name="ReportAmount", parent=styles["ReportCell"], alignment=TA_RIGHT))
    styles["Heading1"].textColor = colors.HexColor(BLUE)

    def cell(value, style="ReportCell"):
        return Paragraph(escape(_text(value)).replace("\n", "<br/>"), styles[style])

    def display(value, heading):
        if isinstance(value, Decimal):
            return inr(value).replace("₹", "").replace("−", "-") if "(INR)" in heading else format(value, "f")
        return value

    generous = {"Trading party", "Product", "Ledger name", "Ledger or total", "Name", "Reference"}
    compact = {"Event", "Unit", "Side"}
    minimum = {"Date": 1.4, "Invoice": 1.65, "Quantity": 1.18, "Journal": 1.05}
    weights = [2.5 if label in generous else 0.85 if label in compact else max(minimum.get(label, 1), min(1.7, len(label) / 12))
               for label in table.columns]
    column_widths = [(document.width - 12) * share / sum(weights) for share in weights]
    rows = [[cell(label, "ReportHead") for label in table.columns]]
    rows.extend([
        cell(display(value, heading), "ReportAmount" if isinstance(value, Decimal) else "ReportCell")
        for value, heading in zip(row, table.columns)
    ] for row in table.rows)
    if not table.rows:
        rows.append([cell("No posted records for this period."), *("" for _ in table.columns[1:])])
    grid = LongTable(rows, colWidths=column_widths, repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BLUE)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5FA")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]
    if not table.rows:
        commands.append(("SPAN", (0, 1), (-1, 1)))
    grid.setStyle(TableStyle(commands))

    def footer(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#344F72"))
        canvas.drawString(27, 14, "Steel Quotes  |  Internal financial report")
        canvas.drawRightString(page[0] - 27, 14, f"Page {doc.page}")

    document.build([
        cell(table.title, "Heading1"),
        cell(f"{start:%d %b %Y} through {end:%d %b %Y}", "BodyText"), Spacer(1, 10), grid,
    ], onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def render_report(table, start, end, format_name):
    if format_name == "csv":
        return _csv(table)
    if format_name == "xlsx":
        return _workbook(table, start, end)
    return _pdf(table, start, end)
