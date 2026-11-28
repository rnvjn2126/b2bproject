from io import BytesIO
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from defusedxml.ElementTree import parse
from django.core.exceptions import ValidationError


def inspect_xlsx_archive(content):
    with ZipFile(BytesIO(content)) as archive:
        members = archive.infolist()
        if len(members) > 40 or sum(part.file_size for part in members) > 4 * 1024 * 1024:
            raise ValidationError("The workbook contains too much expanded data.")
        if len({part.filename for part in members}) != len(members):
            raise ValidationError("The workbook contains repeated archive entries.")
        for part in members:
            if part.compress_type not in (ZIP_STORED, ZIP_DEFLATED):
                raise ValidationError("The workbook uses an unsupported archive compression.")
            name = part.filename.lower()
            if part.flag_bits & 1 or "vbaproject" in name or name.startswith("xl/externallinks/"):
                raise ValidationError("Use an unencrypted XLSX workbook without macros or external workbook links.")
            if name.endswith((".xml", ".rels")):
                with archive.open(part) as source:
                    document = parse(source, forbid_dtd=True)
                if name.endswith(".rels") and any(element.get("TargetMode") == "External"
                                                  for element in document.getroot()):
                    raise ValidationError("Remove external links from the workbook.")
