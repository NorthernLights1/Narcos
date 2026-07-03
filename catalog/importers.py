"""CSV importers (§14, D57): validate the whole file first; post nothing
unless every row is clean. Row errors are reported with their line number."""

import csv
import io
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils.translation import gettext as _

from catalog.models import Customer, Item, ItemUnit, Supplier

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
        if not _check_required(row, i, ["code", "name", "category", "base_unit"], result.errors):
            continue
        category = row["category"].upper()
        if category not in categories:
            result.errors.append(_("row %(n)d: unknown category '%(c)s'")
                                 % {"n": i, "c": row["category"]})
            continue
        batch_default = category in (Item.Category.DRUG, Item.Category.REAGENT)
        fields = {
            "code": row["code"],
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
        if not _check_required(row, i, ["code", "name"], result.errors):
            continue
        fields = {
            "code": row["code"],
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
