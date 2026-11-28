import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from xml.etree.ElementTree import ParseError

from defusedxml.ElementTree import fromstring
from defusedxml.common import DefusedXmlException
from django.core.exceptions import ValidationError
from django.core.validators import DecimalValidator, validate_email

from dashboard.models import Product

from .models import Journal


MAX_BYTES = 512 * 1024
MAX_RECORDS = 500
VOUCHER_KINDS = {
    "sales": Journal.Kind.SALES, "purchase": Journal.Kind.PURCHASE,
    "receipt": Journal.Kind.RECEIPT, "payment": Journal.Kind.PAYMENT,
}
UNITS = {
    "kg": Product.Unit.KG, "kgs": Product.Unit.KG,
    "tonne": Product.Unit.TONNE, "tonnes": Product.Unit.TONNE, "mt": Product.Unit.TONNE,
    "m": Product.Unit.METRE, "mtr": Product.Unit.METRE, "metre": Product.Unit.METRE,
    "nos": Product.Unit.PIECE, "pcs": Product.Unit.PIECE, "piece": Product.Unit.PIECE,
}


@dataclass(frozen=True)
class GroupRow:
    name: str
    parent: str


@dataclass(frozen=True)
class LedgerRow:
    name: str
    parent: str
    opening: Decimal
    email: str = ""
    phone: str = ""
    address: str = ""


@dataclass(frozen=True)
class StockRow:
    name: str
    unit: str


@dataclass(frozen=True)
class VoucherRow:
    key: str
    kind: str
    date: date
    number: str
    narration: str
    lines: tuple[tuple[str, Decimal], ...]


def _text(node, key):
    return (node.findtext(key) or "").strip()


def _required(value, limit, label):
    if not value or len(value) > limit:
        raise ValidationError(f"Enter {label} of up to {limit} characters.")
    return value


def amount(raw):
    raw = str(raw).strip()
    if not re.fullmatch(r"[+-]?\d{1,13}(?:\.\d{1,2})?", raw):
        raise ValidationError("Use an INR amount with at most two decimal places and no currency symbols.")
    value = Decimal(raw).quantize(Decimal("0.01"))
    DecimalValidator(15, 2)(value)
    return value


def _master_name(node, limit):
    return _required(
        (node.get("NAME") or _text(node, "NAME") or _text(node, "LANGUAGENAME.LIST/NAME.LIST/NAME")).strip(),
        limit, "a master name",
    )


def stock_unit(raw):
    unit = UNITS.get(raw.casefold())
    if unit is None:
        raise ValidationError("Use a supported simple stock unit: kg, tonne, metre or piece.")
    return unit


def parse_date(raw):
    if not re.fullmatch(r"\d{8}", raw):
        raise ValidationError("Use a voucher date in YYYYMMDD format.")
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:]))
    except ValueError:
        raise ValidationError("Choose a valid voucher date.") from None


def voucher_row(kind, day, number, key, narration, lines):
    kind = VOUCHER_KINDS.get(kind.casefold())
    if kind is None:
        raise ValidationError("Only sales, purchase, payment and receipt vouchers are supported.")
    day = parse_date(day)
    number = _required(number, 64, "a stable voucher number")
    key = _required(key or f"{kind}/{day}/{number}", 160, "a voucher identity")
    lines = tuple(lines)
    if (not 2 <= len(lines) <= 50 or any(not value for _, value in lines)
            or sum(value for _, value in lines) != 0):
        raise ValidationError("A voucher must have 2–50 nonzero lines with equal total debits and credits.")
    return VoucherRow(key, kind, day, number, _required(narration or f"Imported {kind} {number}", 500, "a narration"), lines)


def _voucher(node):
    for field in ("ISCANCELLED", "ISOPTIONAL", "ISPOSTDATED", "ISDELETED"):
        if _text(node, field).casefold() == "yes":
            raise ValidationError("Cancelled, optional, deleted and postdated vouchers require manual review.")
    if any(child.tag.startswith(("ALLINVENTORYENTRIES", "INVENTORYENTRIES", "INVENTORYALLOCATIONS")) for child in node):
        raise ValidationError("Import accounting-only vouchers without inventory allocations.")
    entries = node.findall("ALLLEDGERENTRIES.LIST")
    alternate = node.findall("LEDGERENTRIES.LIST")
    if entries and alternate:
        raise ValidationError("A voucher cannot mix Tally ledger entry layouts.")
    lines = []
    for entry in entries or alternate:
        if any(child.tag in ("BILLALLOCATIONS.LIST", "BANKALLOCATIONS.LIST", "INVENTORYALLOCATIONS.LIST",
                             "CATEGORYALLOCATIONS.LIST") for child in entry):
            raise ValidationError("Bill, bank, inventory and cost centre allocations require a separately reviewed import.")
        value = amount(_text(entry, "AMOUNT"))
        side = _text(entry, "ISDEEMEDPOSITIVE").casefold()
        if side and side != ("yes" if value < 0 else "no"):
            raise ValidationError("A voucher line has conflicting debit or credit markers.")
        lines.append((_required(_text(entry, "LEDGERNAME"), 120, "a ledger name"), value))
    return voucher_row(
        _text(node, "VOUCHERTYPENAME") or node.get("VCHTYPE", ""), _text(node, "DATE"), _text(node, "VOUCHERNUMBER"),
        _text(node, "GUID") or node.get("REMOTEID", ""), _text(node, "NARRATION"), lines,
    )


def ledger_row(name, parent, opening, email="", phone="", address=""):
    if email:
        validate_email(email)
    if len(phone) > 32 or len(address) > 2000:
        raise ValidationError("Enter a shorter ledger address or phone number.")
    return LedgerRow(_required(name, 120, "a ledger name"), _required(parent, 120, "a ledger parent"),
                     amount(opening or "0"), email, phone, address)


def _record(node):
    action = next((value for key, value in node.attrib.items() if key.casefold() == "action"), "Create")
    if action.strip().casefold() != "create":
        raise ValidationError("Only create or exported records can be imported.")
    if node.tag == "GROUP":
        return GroupRow(_master_name(node, 120), _required(_text(node, "PARENT"), 120, "a parent group"))
    if node.tag == "LEDGER":
        address = "\n".join((line.text or "").strip() for line in node.findall("ADDRESS.LIST/ADDRESS"))
        return ledger_row(_master_name(node, 120), _text(node, "PARENT"), _text(node, "OPENINGBALANCE"),
                          _text(node, "EMAIL"), _text(node, "LEDGERPHONE") or _text(node, "LEDGERMOBILE"), address)
    if node.tag == "STOCKITEM":
        if any(_text(node, key) for key in ("OPENINGBALANCE", "OPENINGVALUE", "OPENINGRATE", "ADDITIONALUNITS")):
            raise ValidationError("Import catalogue-only stock items with one simple unit and no opening quantity or value.")
        return StockRow(_master_name(node, 160), stock_unit(_text(node, "BASEUNITS")))
    if node.tag == "VOUCHER":
        return _voucher(node)
    raise ValidationError(f"Unsupported Tally record type {node.tag[:60]}.")


def parse_tally_xml(content):
    if not isinstance(content, bytes) or not 0 < len(content) <= MAX_BYTES:
        raise ValidationError("Choose a Tally XML file up to 512 KiB.")
    try:
        root = fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ParseError, DefusedXmlException, ValueError):
        raise ValidationError("Choose well-formed XML without declarations, external references or DTDs.") from None
    if root.tag != "ENVELOPE":
        raise ValidationError("The XML needs a Tally ENVELOPE.")
    records = [child for message in root.findall("BODY//TALLYMESSAGE") for child in message if child.tag != "COMPANY"]
    if not 1 <= len(records) <= MAX_RECORDS:
        raise ValidationError(f"Import between one and {MAX_RECORDS} XML records at a time.")
    result = []
    for index, node in enumerate(records, start=1):
        try:
            result.append(_record(node))
        except ValidationError as error:
            raise ValidationError([f"XML record {index}. {message}" for message in error.messages]) from None
    return tuple(result)
