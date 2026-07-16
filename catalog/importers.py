"""CSV importers (§14, D57): validate the whole file first; post nothing
unless every row is clean. Row errors are reported with their line number."""

import csv
import io
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from datetime import datetime, time, timezone as datetime_timezone

from django.db import transaction
from django.utils.translation import gettext as _

from catalog.models import Account, Customer, Item, ItemUnit, Supplier
from docs.models import Document, DocType, DocumentLine
from docs.posting import post
from money.models import PaymentLine
from stock.models import Zone

TRUE_WORDS = {"1", "true", "yes", "y"}
FALSE_WORDS = {"0", "false", "no", "n", ""}


@dataclass
class ImportResult:
    created: int = 0
    errors: list[str] = field(default_factory=list)  # "row N: message"

    @property
    def is_clean(self) -> bool:
        return not self.errors


def _read_rows(uploaded_file) -> tuple[list[dict], list[str]]:
    """Decode + parse; returns (rows, errors). BOM-tolerant."""
    try:
        text = uploaded_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], [_("File is not valid UTF-8 text.")]
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return [], [_("File is empty.")]
    rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            for raw in reader]
    if not rows:
        return [], [_("File has a header but no data rows.")]
    return rows, []


def _parse_bool(value: str, row_no: int, column: str, errors: list[str]) -> bool:
    word = value.strip().lower()
    if word in TRUE_WORDS:
        return True
    if word in FALSE_WORDS:
        return False
    errors.append(_("row %(n)d: %(col)s must be yes/no, got '%(v)s'")
                  % {"n": row_no, "col": column, "v": value})
    return False


def _parse_decimal(value: str, row_no: int, column: str, errors: list[str],
                   default: Decimal | None = None) -> Decimal | None:
    if value == "":
        return default
    try:
        return Decimal(value)
    except InvalidOperation:
        errors.append(_("row %(n)d: %(col)s is not a number: '%(v)s'")
                      % {"n": row_no, "col": column, "v": value})
        return default


def _parse_date(value: str, row_no: int, column: str, errors: list[str]):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        errors.append(_("row %(n)d: %(col)s must be YYYY-MM-DD, got '%(v)s'")
                      % {"n": row_no, "col": column, "v": value})
        return None


def _as_datetime(day):
    if day is None:
        return None
    return datetime.combine(day, time.min, tzinfo=datetime_timezone.utc)


def _check_required(row: dict, row_no: int, columns: list[str], errors: list[str]) -> bool:
    ok = True
    for col in columns:
        if not row.get(col):
            errors.append(_("row %(n)d: missing %(col)s") % {"n": row_no, "col": col})
            ok = False
    return ok


def _check_duplicate_codes(rows: list[dict], model, errors: list[str]) -> None:
    seen: dict[str, int] = {}
    for i, row in enumerate(rows, start=2):
        code = row.get("code", "")
        if not code:
            continue
        if code in seen:
            errors.append(_("row %(n)d: duplicate code '%(c)s' (also on row %(m)d)")
                          % {"n": i, "c": code, "m": seen[code]})
        seen[code] = i
    existing = set(
        model.objects.filter(code__in=seen).values_list("code", flat=True)
    )
    for code, row_no in seen.items():
        if code in existing:
            errors.append(_("row %(n)d: code '%(c)s' already exists")
                          % {"n": row_no, "c": code})


def _parse_alt_units(value: str, row_no: int, errors: list[str]) -> list[tuple[str, int]]:
    """Format: 'carton:12; box:144' — label:whole-number factor pairs."""
    units: list[tuple[str, int]] = []
    if not value:
        return units
    for part in value.split(";"):
        part = part.strip()
        if not part:
            continue
        label, sep, factor_text = part.partition(":")
        try:
            factor = int(factor_text)
        except ValueError:
            factor = 0
        if not sep or not label.strip() or factor <= 1:
            errors.append(
                _("row %(n)d: bad alt_units part '%(p)s' (need label:factor, factor > 1)")
                % {"n": row_no, "p": part}
            )
            continue
        units.append((label.strip(), factor))
    return units


def import_items(uploaded_file) -> ImportResult:
    rows, errors = _read_rows(uploaded_file)
    result = ImportResult(errors=errors)
    if errors:
        return result

    categories = {c.value for c in Item.Category}
    parsed: list[tuple[dict, list[tuple[str, int]]]] = []
    _check_duplicate_codes(rows, Item, result.errors)
    for i, row in enumerate(rows, start=2):
        # code is optional — blank codes are auto-assigned at save (AutoCodeModel)
        if not _check_required(row, i, ["name", "category", "base_unit"], result.errors):
            continue
        category = row["category"].upper()
        if category not in categories:
            result.errors.append(_("row %(n)d: unknown category '%(c)s'")
                                 % {"n": i, "c": row["category"]})
            continue
        batch_default = category in (Item.Category.DRUG, Item.Category.REAGENT)
        fields = {
            "code": row.get("code", ""),
            "name": row["name"],
            "category": category,
            "base_unit": row["base_unit"],
            "is_batch_tracked": _parse_bool(row.get("is_batch_tracked", "1" if batch_default else "0"), i, "is_batch_tracked", result.errors),
            "has_expiry": _parse_bool(row.get("has_expiry", "1" if batch_default else "0"), i, "has_expiry", result.errors),
            "vat_exempt": _parse_bool(row.get("vat_exempt", "0"), i, "vat_exempt", result.errors),
            "maintained_price": _parse_decimal(row.get("maintained_price", ""), i, "maintained_price", result.errors, Decimal("0")),
            "generic_name": row.get("generic_name", ""),
            "dosage_form": row.get("dosage_form", ""),
            "strength": row.get("strength", ""),
            "pack_description": row.get("pack_description", ""),
            "shelf_bin": row.get("shelf_bin", ""),
        }
        reorder = row.get("reorder_level", "")
        if reorder:
            if reorder.isdigit():
                fields["reorder_level"] = int(reorder)
            else:
                result.errors.append(_("row %(n)d: reorder_level is not a whole number")
                                     % {"n": i})
        if fields["has_expiry"] and not fields["is_batch_tracked"]:
            result.errors.append(
                _("row %(n)d: has_expiry requires is_batch_tracked") % {"n": i}
            )
        if fields["maintained_price"] <= 0:
            # D81: imported items are maintained-price; a priceless item
            # would be unsellable (and invites ad-hoc prices on documents).
            result.errors.append(
                _("row %(n)d: maintained_price must be greater than 0 — "
                  "every item needs a selling price") % {"n": i}
            )
        units = _parse_alt_units(row.get("alt_units", ""), i, result.errors)
        parsed.append((fields, units))

    if not result.is_clean:
        return result

    with transaction.atomic():
        for fields, units in parsed:
            item = Item.objects.create(**fields)
            for label, factor in units:
                ItemUnit.objects.create(item=item, unit_label=label, factor_to_base=factor)
            result.created += 1
    return result


def _import_party(uploaded_file, model, extra_parser=None) -> ImportResult:
    rows, errors = _read_rows(uploaded_file)
    result = ImportResult(errors=errors)
    if errors:
        return result

    parsed: list[dict] = []
    _check_duplicate_codes(rows, model, result.errors)
    for i, row in enumerate(rows, start=2):
        # code is optional — blank codes are auto-assigned at save (AutoCodeModel)
        if not _check_required(row, i, ["name"], result.errors):
            continue
        fields = {
            "code": row.get("code", ""),
            "name": row["name"],
            "tin": row.get("tin", ""),
            "phone": row.get("phone", ""),
            "address": row.get("address", ""),
        }
        if extra_parser:
            extra_parser(row, i, fields, result.errors)
        parsed.append(fields)

    if not result.is_clean:
        return result
    with transaction.atomic():
        for fields in parsed:
            model.objects.create(**fields)
            result.created += 1
    return result


def import_customers(uploaded_file) -> ImportResult:
    def extra(row, row_no, fields, errors):
        fields["credit_limit"] = _parse_decimal(
            row.get("credit_limit", ""), row_no, "credit_limit", errors
        )
        fields["is_withholding_agent"] = _parse_bool(
            row.get("is_withholding_agent", "0"), row_no, "is_withholding_agent", errors
        )

    return _import_party(uploaded_file, Customer, extra)


def import_suppliers(uploaded_file) -> ImportResult:
    return _import_party(uploaded_file, Supplier)


def import_opening_stock(uploaded_file, actor) -> ImportResult:
    rows, errors = _read_rows(uploaded_file)
    result = ImportResult(errors=errors)
    if errors:
        return result

    parsed = []
    for i, row in enumerate(rows, start=2):
        if not _check_required(row, i, ["item_code", "qty", "unit_cost"], result.errors):
            continue
        item = Item.objects.filter(code=row["item_code"]).first()
        if item is None:
            result.errors.append(_("row %(n)d: unknown item_code '%(c)s'")
                                 % {"n": i, "c": row["item_code"]})
            continue
        qty_text = row["qty"]
        if not qty_text.isdigit() or int(qty_text) <= 0:
            result.errors.append(_("row %(n)d: qty must be a positive whole number")
                                 % {"n": i})
        cost = _parse_decimal(row["unit_cost"], i, "unit_cost", result.errors)
        expiry = _parse_date(row.get("expiry", ""), i, "expiry", result.errors)
        document_date = _parse_date(row.get("document_date", ""), i, "document_date", result.errors)
        if item.is_batch_tracked and not row.get("batch_no"):
            result.errors.append(_("row %(n)d: batch_no required for %(item)s")
                                 % {"n": i, "item": item.code})
        if item.has_expiry and expiry is None:
            result.errors.append(_("row %(n)d: expiry required for %(item)s")
                                 % {"n": i, "item": item.code})
        parsed.append((item, row.get("batch_no", ""), expiry,
                       int(qty_text) if qty_text.isdigit() else 0,
                       cost, document_date))

    if not result.is_clean:
        return result
    with transaction.atomic():
        doc = Document.objects.create(
            doc_type=DocType.OPENING_STOCK, created_by=actor,
            document_date=_as_datetime(parsed[0][5]) if parsed else None,
            notes="CSV opening stock import",
        )
        for item, batch_no, expiry, qty, cost, _document_date in parsed:
            DocumentLine.objects.create(
                document=doc, item=item, batch_no_entered=batch_no,
                expiry_entered=expiry, unit_label=item.base_unit, factor=1,
                qty_entered=qty, unit_cost_entered=cost,
            )
        post(doc, actor)
        result.created = len(parsed)
    return result


def _import_opening_party(uploaded_file, actor, party_model, doc_type, party_field) -> ImportResult:
    rows, errors = _read_rows(uploaded_file)
    result = ImportResult(errors=errors)
    if errors:
        return result

    parsed = []
    for i, row in enumerate(rows, start=2):
        if not _check_required(row, i, ["code", "amount", "document_date"], result.errors):
            continue
        party = party_model.objects.filter(code=row["code"]).first()
        if party is None:
            result.errors.append(_("row %(n)d: unknown code '%(c)s'")
                                 % {"n": i, "c": row["code"]})
            continue
        amount = _parse_decimal(row["amount"], i, "amount", result.errors)
        document_date = _parse_date(row["document_date"], i, "document_date", result.errors)
        due_date = _parse_date(row.get("due_date", ""), i, "due_date", result.errors)
        if amount is not None and amount <= 0:
            result.errors.append(_("row %(n)d: amount must be positive") % {"n": i})
        parsed.append((party, amount, document_date, due_date, row.get("notes", "")))

    if not result.is_clean:
        return result
    with transaction.atomic():
        for party, amount, document_date, due_date, notes in parsed:
            fields = {
                "doc_type": doc_type,
                "created_by": actor,
                "document_date": _as_datetime(document_date),
                "due_date": due_date,
                "grand_total": amount,
                "notes": notes,
                party_field: party,
            }
            post(Document.objects.create(**fields), actor)
            result.created += 1
    return result


def import_opening_ar(uploaded_file, actor) -> ImportResult:
    return _import_opening_party(uploaded_file, actor, Customer,
                                 DocType.OPENING_AR, "customer")


def import_opening_ap(uploaded_file, actor) -> ImportResult:
    return _import_opening_party(uploaded_file, actor, Supplier,
                                 DocType.OPENING_AP, "supplier")


def import_opening_cash(uploaded_file, actor) -> ImportResult:
    rows, errors = _read_rows(uploaded_file)
    result = ImportResult(errors=errors)
    if errors:
        return result

    parsed = []
    for i, row in enumerate(rows, start=2):
        if not _check_required(row, i, ["account", "amount"], result.errors):
            continue
        account = Account.objects.filter(name=row["account"]).first()
        if account is None:
            result.errors.append(_("row %(n)d: unknown account '%(a)s'")
                                 % {"n": i, "a": row["account"]})
            continue
        amount = _parse_decimal(row["amount"], i, "amount", result.errors)
        document_date = _parse_date(row.get("document_date", ""), i, "document_date", result.errors)
        if amount is not None and amount <= 0:
            result.errors.append(_("row %(n)d: amount must be positive") % {"n": i})
        parsed.append((account, amount, document_date))

    if not result.is_clean:
        return result
    with transaction.atomic():
        doc = Document.objects.create(
            doc_type=DocType.OPENING_CASH, created_by=actor,
            document_date=_as_datetime(parsed[0][2]) if parsed else None,
            notes="CSV opening cash import",
        )
        for account, amount, _document_date in parsed:
            PaymentLine.objects.create(document=doc, account=account, amount=amount)
        post(doc, actor)
        result.created = len(parsed)
    return result
