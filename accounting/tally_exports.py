from collections import defaultdict
from xml.etree.ElementTree import Element, SubElement, tostring

from django.core.exceptions import PermissionDenied, ValidationError

from .models import JournalLine
from .tally_xml import MAX_RECORDS, VOUCHER_KINDS, parse_tally_xml


def export_tally_vouchers(workspace, actor, start, end):
    if workspace.owner_id != actor.pk or not actor.is_active:
        raise PermissionDenied
    if start > end:
        raise ValidationError("Choose a valid date range for the export.")
    kinds = {kind: label.title() for label, kind in VOUCHER_KINDS.items()}
    lines = JournalLine.objects.filter(
        journal__workspace=workspace, journal__sealed=True, journal__date__range=(start, end),
        journal__kind__in=kinds, ledger__workspace=workspace, ledger__group__workspace=workspace,
    ).select_related("journal", "ledger").order_by("journal__date", "journal_id", "pk")
    grouped = defaultdict(list)
    for line in lines.iterator():
        grouped[line.journal].append(line)
        if len(grouped) > MAX_RECORDS:
            raise ValidationError("Choose a date range with at most 500 supported vouchers.")
    if not grouped:
        raise ValidationError("No supported posted accounting vouchers exist for these dates.")

    root = Element("ENVELOPE")
    header = SubElement(root, "HEADER")
    for key, value in (("VERSION", "1"), ("TALLYREQUEST", "Import"), ("TYPE", "Data"), ("ID", "Vouchers")):
        SubElement(header, key).text = value
    data = SubElement(SubElement(root, "BODY"), "DATA")
    for journal, rows in grouped.items():
        if journal.reverses_id is not None or hasattr(journal, "reversal"):
            raise ValidationError("Choose a range without reversed vouchers. Export their corrections from the day book.")
        node = SubElement(SubElement(data, "TALLYMESSAGE"), "VOUCHER", {"ACTION": "Create"})
        for field, value in (
            ("DATE", journal.date.strftime("%Y%m%d")), ("VOUCHERTYPENAME", kinds[journal.kind]),
            ("VOUCHERNUMBER", journal.transaction_reference), ("NARRATION", journal.narration),
            ("GUID", str(journal.submission_key)),
        ):
            SubElement(node, field).text = value
        for row in rows:
            ledger = SubElement(node, "ALLLEDGERENTRIES.LIST")
            debit = row.side == JournalLine.Side.DEBIT
            SubElement(ledger, "LEDGERNAME").text = row.ledger.name
            SubElement(ledger, "ISDEEMEDPOSITIVE").text = "Yes" if debit else "No"
            SubElement(ledger, "AMOUNT").text = f"{-row.amount if debit else row.amount:.2f}"
    content = tostring(root, encoding="utf-8", xml_declaration=True)
    parse_tally_xml(content)
    return content
