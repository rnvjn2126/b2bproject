from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def sales_order_pdf(order):
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, pageCompression=0)
    styles = getSampleStyleSheet()

    def paragraph(value, style="BodyText"):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), styles[style])

    story = [
        paragraph(f"Sales order {order.number}", "Heading1"),
        paragraph(order.workspace.name),
        paragraph("Order confirmation. This document is not a tax invoice."),
        paragraph(f"Customer: {order.customer_name}"),
        paragraph(order.customer_address or "Address not recorded"),
        paragraph(f"Customer purchase order: {order.customer_reference or 'Not provided'}"),
        paragraph(f"Requested delivery: {order.delivery_on or 'To be confirmed'}"),
        Spacer(1, 10),
    ]
    rows = [["Item", "Quantity", "Unit", "Rate (INR)", "Total (INR)"]]
    for line in order.lines.all():
        item = " · ".join(part for part in (line.description, line.grade, line.dimensions) if part)
        rows.append([paragraph(item), f"{line.quantity:f}", line.unit, f"{line.unit_price:.4f}", f"{line.total:.2f}"])
    table = Table(rows, colWidths=[190, 65, 40, 75, 75], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe8f4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.lightgrey),
    ]))
    story.extend([table, Spacer(1, 10), paragraph(f"Subtotal before tax: INR {order.subtotal:.2f}")])
    if order.payment_terms:
        story.append(paragraph(f"Payment terms: {order.payment_terms}"))
    if order.delivery_terms:
        story.append(paragraph(f"Delivery terms: {order.delivery_terms}"))
    document.build(story)
    return buffer.getvalue()


def purchase_order_pdf(purchase):
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, pageCompression=0)
    styles = getSampleStyleSheet()
    item = purchase.requirement
    fields = [
        f"Purchase order {purchase.number}",
        item.order.workspace.name,
        f"Supplier: {purchase.supplier_name}",
        f"Supplier reference: {purchase.supplier_reference or 'Not provided'}",
        f"Expected delivery: {purchase.delivery_on}",
        f"Item: {item.description} {item.grade} {item.dimensions}",
        f"Quantity: {purchase.quantity:f} {item.unit}",
        f"Material rate: INR {purchase.unit_price:.4f} per {item.unit}",
        f"Material subtotal: INR {purchase.total:.2f}",
        "Material order before freight and tax. This document is not a tax invoice.",
    ]
    document.build([
        Paragraph(escape(field), styles["Heading1" if index == 0 else "BodyText"])
        for index, field in enumerate(fields)
    ])
    return buffer.getvalue()
