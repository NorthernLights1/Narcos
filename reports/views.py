import csv
import datetime as dt
from collections import Counter
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _

from django.db.models import Count, OuterRef, Subquery

from catalog.models import Account, Customer, Item, Supplier
from core.ethiopian_calendar import fiscal_year_bounds
from core.models import CompanySettings
from core.preferences import REPORT_FILTERS, restore_filters
from docs.checks import ExpiryStatus, expiry_status
from docs.forms import _selling_price
from docs.handlers_payments import (
    AP_TARGET_TYPES,
    AR_TARGET_TYPES,
    open_balance,
    withholding_balance,
)
from docs.models import DocType, Document, DocumentLine
from money.models import (
    MoneyLedger,
    PartyLedger,
    PaymentAllocation,
    WithholdingLedger,
    account_balance,
)
from stock.models import CostLot, StockBalance, StockLedger, Zone


def _day(value):
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return timezone.localdate(value)
    return value


def _in_range(value, start, end) -> bool:
    day = _day(value)
    return day is not None and start <= day <= end


def _selected_range(request):
    today = timezone.localdate()
    settings = CompanySettings.load()
    period = request.GET.get("period", "this_fy")
    if period == "last_fy":
        _fy, start, _end = fiscal_year_bounds(today, settings.fiscal_year_start_month)
        _fy, start, end = fiscal_year_bounds(start - dt.timedelta(days=1),
                                             settings.fiscal_year_start_month)
    elif period == "custom":
        start = _parse_date(request.GET.get("start")) or today
        end = _parse_date(request.GET.get("end")) or today
        if end < start:
            start, end = end, start
    else:
        period = "this_fy"
        _fy, start, end = fiscal_year_bounds(today, settings.fiscal_year_start_month)
    return period, start, end


def _parse_date(value):
    try:
        return dt.date.fromisoformat(value or "")
    except ValueError:
        return None


def _posted_documents(doc_types, start, end):
    rows = (
        Document.objects.filter(doc_type__in=doc_types, status=Document.Status.POSTED)
        .select_related("customer", "supplier", "expense_category")
        .prefetch_related("lines__item", "lines__batch", "charges")
        .order_by("document_date", "pk")
    )
    for doc in rows:
        if _in_range(doc.document_date, start, end):
            yield doc


def _money(value):
    return value.quantize(Decimal("0.01"))


def _stock_on_hand(_start, _end, _user):
    columns = [_("Item"), _("Name"), _("Batch"), _("Expiry"), _("Zone"),
               _("Customer"), _("Qty")]
    rows = []
    balances = (
        StockBalance.objects.filter(qty__gt=0)
        .select_related("item", "batch", "consignment_customer")
        .order_by("item__code", "batch__expiry_date", "zone")
    )
    for balance in balances:
        rows.append([
            balance.item.code, balance.item.name,
            balance.batch.batch_no if balance.batch else "",
            balance.batch.expiry_date if balance.batch else "",
            balance.get_zone_display(),
            balance.consignment_customer.name if balance.consignment_customer else "",
            balance.qty,
        ])
    return columns, rows, []


def _stock_movement(start, end, _user):
    columns = [_("Date"), _("Document"), _("Type"), _("Item"), _("Batch"),
               _("Zone"), _("Customer"), _("Qty")]
    rows = []
    moves = (
        StockLedger.objects.select_related(
            "document", "item", "batch", "consignment_customer",
        )
        .order_by("at", "pk")
    )
    for move in moves:
        if not _in_range(move.at, start, end):
            continue
        rows.append([
            _day(move.at), move.document.doc_no, move.document.get_doc_type_display(),
            move.item.code, move.batch.batch_no if move.batch else "",
            move.get_zone_display(),
            move.consignment_customer.name if move.consignment_customer else "",
            move.qty_delta,
        ])
    return columns, rows, []


def _expiry(start, end, _user):
    today = timezone.localdate()
    settings = CompanySettings.load()
    columns = [_("Status"), _("Item"), _("Batch"), _("Expiry"), _("Zone"), _("Qty")]
    rows = []
    balances = (
        StockBalance.objects.filter(qty__gt=0, batch__expiry_date__isnull=False)
        .select_related("item", "batch")
        .order_by("batch__expiry_date", "item__code")
    )
    for balance in balances:
        status = expiry_status(balance.batch.expiry_date, today, settings.near_expiry_months)
        if status == ExpiryStatus.OK:
            continue
        rows.append([
            _("Expired") if status == ExpiryStatus.EXPIRED else _("Near expiry"),
            balance.item.code, balance.batch.batch_no, balance.batch.expiry_date,
            balance.get_zone_display(), balance.qty,
        ])
    return columns, rows, []


def _low_stock(_start, _end, _user):
    columns = [_("Item"), _("Name"), _("Warehouse qty"), _("Reorder level")]
    rows = []
    for item in Item.objects.filter(reorder_level__isnull=False).order_by("code"):
        qty = 0
        for balance in item.stockbalance_set.filter(zone=Zone.WAREHOUSE):
            qty += balance.qty
        if qty <= item.reorder_level:
            rows.append([item.code, item.name, qty, item.reorder_level])
    return columns, rows, []


def _valuation(_start, _end, _user):
    columns = [_("Item"), _("Batch"), _("Zone"), _("Qty"), _("Unit cost"), _("Value")]
    rows = []
    total = Decimal("0.00")
    balances = (
        StockBalance.objects.filter(qty__gt=0)
        .select_related("item", "batch", "lot")
        .order_by("item__code", "zone")
    )
    for balance in balances:
        value = _money(Decimal(balance.qty) * balance.lot.unit_cost)
        total += value
        rows.append([
            balance.item.code,
            balance.batch.batch_no if balance.batch else "",
            balance.get_zone_display(),
            balance.qty,
            balance.lot.unit_cost,
            value,
        ])
    return columns, rows, [_("Total"), "", "", "", "", _money(total)]


SALE_SIDE_TYPES = [DocType.SALE, DocType.CONSIGNMENT_SETTLEMENT,
                   DocType.CUSTOMER_RETURN]


def _extra_row(doc, label, amount):
    """R75: money on the document that belongs to no item.

    `line_net` carries line discounts only. A delivery charge is money the
    customer paid and a document discount is money they did not, so a report
    built from lines alone disagrees with the invoice it came from by exactly
    `charges − doc_discount`. They cost nothing to make, so they carry no COGS
    and are all profit or all loss. They belong to no brand and no generic,
    which is why a brand filter drops them (D141).
    """
    return {
        "date": _day(doc.document_date), "doc_no": doc.doc_no,
        "doc_pk": doc.pk, "customer": doc.customer.name,
        "code": "", "generic": "", "brand": "", "strength": "",
        "label": label, "is_extra": True, "qty": None,
        "revenue": amount, "cogs": _money(Decimal("0.00")), "profit": amount,
    }


def _matches(row, filters) -> bool:
    """D141: document number, generic and brand, each a case-insensitive
    fragment. An extras row has no item, so a question about a brand or a
    generic cannot include it — keeping it would inflate that brand."""
    doc = (filters.get("doc") or "").strip().casefold()
    generic = (filters.get("generic") or "").strip().casefold()
    brand = (filters.get("brand") or "").strip().casefold()
    if doc and doc not in row["doc_no"].casefold():
        return False
    if (generic or brand) and row["is_extra"]:
        return False
    if generic and generic not in row["generic"].casefold():
        return False
    if brand and brand not in row["brand"].casefold():
        return False
    return True


def _sale_line_rows(start, end, filters=None):
    """Every posted sale-side line as its own row, item named in full.

    The row **is** the line: quantity, revenue and cost are that one item's,
    never the document's. That was always true; D141 is what makes it legible,
    because a bare item code left the reader unable to tell.

    Quantity is `qty_base`, except on a settlement where only `qty_sold` was
    actually sold. A return is the same goods coming back, so it signs
    negative on every number and nets out of the total.
    """
    rows = []
    for doc in _posted_documents(SALE_SIDE_TYPES, start, end):
        sign = Decimal("-1.00") if doc.doc_type == DocType.CUSTOMER_RETURN \
            else Decimal("1.00")
        for line in doc.lines.all():
            qty = (line.qty_sold if doc.doc_type == DocType.CONSIGNMENT_SETTLEMENT
                   else line.qty_base)
            revenue = _money(sign * line.line_net)
            cogs = _money(sign * line.cogs_total)
            rows.append({
                "date": _day(doc.document_date), "doc_no": doc.doc_no,
                "doc_pk": doc.pk, "customer": doc.customer.name,
                "code": line.item.code, "generic": line.item.generic_name,
                "brand": line.item.name, "strength": line.item.strength,
                "label": "", "is_extra": False, "qty": int(sign) * qty,
                "revenue": revenue, "cogs": cogs,
                "profit": _money(revenue - cogs),
            })
        for charge in doc.charges.all():
            rows.append(_extra_row(doc, charge.label, _money(sign * charge.amount)))
        if doc.doc_discount:
            rows.append(_extra_row(doc, _("Document discount"),
                                   _money(-sign * doc.doc_discount)))

    kept = [row for row in rows if _matches(row, filters or {})]
    totals = {"revenue": Decimal("0.00"), "cogs": Decimal("0.00")}
    for row in kept:
        totals["revenue"] += row["revenue"]
        totals["cogs"] += row["cogs"]
    totals["profit"] = _money(totals["revenue"] - totals["cogs"])
    totals["revenue"] = _money(totals["revenue"])
    totals["cogs"] = _money(totals["cogs"])
    return kept, totals


# --- D126: what each product actually sold for ---------------------------

def _achieved_rows(start, end, show_cost, key):
    """Group posted sales revenue by product, and show the price actually
    achieved per base unit.

    `line_net` carries line discounts only. Document discounts and delivery
    charges live on the document (R75), so they are deliberately excluded
    here: this is a *line-level* achieved price, and it will not reconcile to
    an invoice carrying a document discount. The column header says so.

    Quantity is `qty_base`, never `qty_entered`. Posting computes revenue as
    `qty_entered × unit_price` while stock moves `qty_entered × factor`, so
    dividing by the entered quantity would mix carton prices with single
    prices the moment a pack factor is in play.
    """
    buckets: dict = {}
    for doc in _posted_documents(
        [DocType.SALE, DocType.CONSIGNMENT_SETTLEMENT, DocType.CUSTOMER_RETURN],
        start, end,
    ):
        sign = Decimal("-1.00") if doc.doc_type == DocType.CUSTOMER_RETURN else Decimal("1.00")
        for line in doc.lines.select_related("item"):
            qty = line.qty_sold if doc.doc_type == DocType.CONSIGNMENT_SETTLEMENT \
                else line.qty_base
            if not qty:
                continue
            group, display = key(line.item)
            bucket = buckets.setdefault(group, {
                "qty": 0, "revenue": Decimal("0.00"), "cogs": Decimal("0.00"),
                "prices": [], "names": Counter(),
            })
            bucket["names"][display] += 1
            revenue = _money(sign * line.line_net)
            bucket["qty"] += int(sign) * qty
            bucket["revenue"] += revenue
            bucket["cogs"] += _money(sign * line.cogs_total)
            # A return is the same price going back out; it should not read as
            # a separate, negative "achieved price".
            bucket["prices"].append(_money(abs(line.line_net) / qty))

    rows = []
    totals = {"qty": 0, "revenue": Decimal("0.00"), "cogs": Decimal("0.00")}
    for group in sorted(buckets):
        b = buckets[group]
        # Most common exact spelling wins, alphabetical tie-break so the same
        # data always renders the same row. This is the rule the eventual
        # `Generic` backfill will use, so the report previews its grouping.
        label = sorted(b["names"].items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        totals["qty"] += b["qty"]
        totals["revenue"] += b["revenue"]
        totals["cogs"] += b["cogs"]
        prices = b["prices"]
        average = _money(b["revenue"] / b["qty"]) if b["qty"] else _money(Decimal("0.00"))
        row = [label, b["qty"], b["revenue"], average, min(prices), max(prices)]
        if show_cost:
            row.extend([b["cogs"], _money(b["revenue"] - b["cogs"])])
        rows.append(row)
    return rows, totals


def _achieved_report(start, end, user, key, heading):
    columns = [heading, _("Qty (base)"), _("Revenue"),
               _("Avg price / base unit"), _("Lowest"), _("Highest")]
    if user.is_owner:
        columns.extend([_("COGS"), _("Profit")])
    rows, totals = _achieved_rows(start, end, user.is_owner, key)
    total = [_("Total"), totals["qty"], _money(totals["revenue"]), "", "", ""]
    if user.is_owner:
        total.extend([_money(totals["cogs"]),
                      _money(totals["revenue"] - totals["cogs"])])
    return columns, rows, total


def _brand_key(item):
    label = f"{item.code} — {item.name}"
    return label, label


def fold_generic(value: str):
    """(key, label) for one generic name.

    Fold case and surrounding space, because those are provably the same
    generic. A real misspelling is not — `Paracetamoll` stays its own row, and
    that split is the argument for giving the catalogue a generic of its own.
    The grand total is unaffected either way; only the split moves.

    D144 made this a function of its own so the grouped sales report and
    `sales-by-generic` cannot drift apart about what one generic is.
    """
    cleaned = " ".join((value or "").split())
    if not cleaned:
        unset = _("(no generic set)")
        return unset, unset
    return cleaned.casefold(), cleaned


def _generic_key(item):
    return fold_generic(item.generic_name)


def _sales_by_brand(start, end, user):
    return _achieved_report(start, end, user, key=_brand_key, heading=_("Brand"))


def _sales_by_generic(start, end, user):
    return _achieved_report(start, end, user, key=_generic_key, heading=_("Generic"))


def _profit(start, end, _user):
    _rows, totals = _sale_line_rows(start, end)
    revenue, cogs = totals["revenue"], totals["cogs"]
    expenses = Decimal("0.00")
    for doc in _posted_documents([DocType.EXPENSE], start, end):
        expenses += doc.grand_total
    gross_profit = revenue - cogs
    return [_("Metric"), _("Amount")], [
        [_("Sales revenue"), _money(revenue)],
        [_("COGS"), _money(cogs)],
        [_("Gross profit"), _money(gross_profit)],
        [_("Expenses"), _money(expenses)],
        [_("Net profit"), _money(gross_profit - expenses)],
    ], []


def _losses(start, end, _user):
    columns = [_("Date"), _("Document"), _("Zone"), _("Item"), _("Qty"),
               _("Unit cost"), _("Value")]
    rows = []
    total = Decimal("0.00")
    moves = (
        StockLedger.objects.filter(zone__in=[Zone.EXPIRED, Zone.UNFIT, Zone.DISPOSED])
        .exclude(document__doc_type=DocType.OPENING_EXPIRED)
        .select_related("document", "item", "lot")
        .order_by("at", "pk")
    )
    for move in moves:
        if not _in_range(move.at, start, end):
            continue
        value = _money(Decimal(move.qty_delta) * move.lot.unit_cost)
        total += value
        rows.append([
            _day(move.at), move.document.doc_no, move.get_zone_display(),
            move.item.code, move.qty_delta, move.lot.unit_cost, value,
        ])
    return columns, rows, [_("Total"), "", "", "", "", "", _money(total)]


def _aging(doc_types, party_label, _start, _end):
    """Open items as of today — deliberately ignores the period filter (D73):
    an unpaid invoice stays visible no matter how old it is."""
    columns = [_("Date"), _("Due"), _("Document"), party_label,
               _("Original"), _("Settled"), _("Open"), _("Days")]
    rows = []
    today = timezone.localdate()
    docs = (
        Document.objects.filter(doc_type__in=doc_types, status=Document.Status.POSTED)
        .select_related("customer", "supplier")
        .order_by("document_date", "pk")
    )
    for doc in docs:
        if doc.doc_type == DocType.SALE and doc.sale_kind != Document.SaleKind.CREDIT:
            continue
        if doc.doc_type == DocType.CONSIGNMENT_SETTLEMENT \
                and doc.sale_kind != Document.SaleKind.CREDIT:
            continue
        balance = open_balance(doc)
        if balance <= 0:
            continue
        anchor = doc.due_date or _day(doc.document_date)
        rows.append([
            _day(doc.document_date), doc.due_date or "", doc.doc_no,
            doc.customer.name if doc.customer_id else doc.supplier.name,
            doc.grand_total, _money(doc.grand_total - balance), balance,
            max((today - anchor).days, 0),
        ])
    return columns, rows, []


def _ar_aging(start, end, _user):
    return _aging(
        [DocType.SALE, DocType.CONSIGNMENT_SETTLEMENT, DocType.OPENING_AR],
        _("Customer"), start, end,
    )


def _ap_aging(start, end, _user):
    return _aging([DocType.RECEIVING, DocType.OPENING_AP], _("Supplier"), start, end)


def _balances_as_of(party_type, model, party_label, end):
    """One row per party with a non-zero balance on `end` (client request):
    a snapshot, deliberately without due dates — aging answers 'how late',
    this answers 'who owed what on that day'. Ties out with each party's
    statement closing balance and with the Finance page totals."""
    columns = [_("Code"), party_label, _("Balance")]
    balances: dict[int, Decimal] = {}
    rows_qs = (PartyLedger.objects.filter(party_type=party_type)
               .select_related("document"))
    for row in rows_qs:
        day = _day(row.document.document_date)
        if day is None or day > end:
            continue
        balances[row.party_id] = (
            balances.get(row.party_id, Decimal("0.00")) + row.amount_delta
        )
    parties = {p.pk: p for p in model.objects.filter(pk__in=balances)}
    rows = []
    grand = Decimal("0.00")
    for pk, balance in balances.items():
        if balance == 0:
            continue
        party = parties[pk]
        rows.append([party.code, party.name, balance])
        grand += balance
    rows.sort(key=lambda r: r[2], reverse=True)  # biggest balance first
    return columns, rows, [_("Total"), "", _money(grand)]


def _normalised_tin(value: str) -> str:
    """D127: tax numbers are typed by people, so `0012345678`, ` 0012345678 `
    and `001-2345678` are one number. Fold spaces, hyphens and case before
    comparing. Blank stays blank and never matches anything — pairing empty
    strings would marry every business without a tax number to every other.
    """
    return "".join((value or "").split()).replace("-", "").replace(".", "").casefold()


def _party_totals(party_type, end) -> dict:
    """Balance per party id on `end`, from the ledger alone."""
    balances: dict[int, Decimal] = {}
    for row in PartyLedger.objects.filter(party_type=party_type).select_related("document"):
        day = _day(row.document.document_date)
        if day is None or day > end:
            continue
        balances[row.party_id] = balances.get(row.party_id, Decimal("0.00")) + row.amount_delta
    return balances


def _both_faces(_start, end, _user):
    """D127: the net position of a business that is both customer and supplier.

    The statement page already pairs one party with its other face; this is the
    same question asked across everyone at once, which is what the client
    actually described. Pairing is still by tax number — an explicit link needs
    a migration and waits for a look at the real data (R95) — so the report is
    honest about what it could not pair rather than quietly dropping it.

    **Nothing is netted in the books.** D79 settled that: each side settles
    with its own payment documents, which is what tax filing needs. The
    difference here is information on a report, and the sign convention is
    spelled out in the column name.
    """
    columns = [_("Business"), _("Customer"), _("Supplier"),
               _("Receivable"), _("Payable"), _("Net (+ = due to us)")]
    receivable = _party_totals(PartyLedger.PartyType.CUSTOMER, end)
    payable = _party_totals(PartyLedger.PartyType.SUPPLIER, end)
    customers = {c.pk: c for c in Customer.objects.all()}
    suppliers = {s.pk: s for s in Supplier.objects.all()}

    # Group both sides by a normalised tax number. Blank never pairs — matching
    # empty strings would marry every business without a TIN to every other.
    by_tin: dict[str, dict] = {}
    for party in customers.values():
        tin = _normalised_tin(party.tin)
        if tin:
            by_tin.setdefault(tin, {"customers": [], "suppliers": []})["customers"].append(party)
    for party in suppliers.values():
        tin = _normalised_tin(party.tin)
        if tin:
            by_tin.setdefault(tin, {"customers": [], "suppliers": []})["suppliers"].append(party)

    rows = []
    for tin in sorted(by_tin):
        pair = by_tin[tin]
        if not (pair["customers"] and pair["suppliers"]):
            continue  # only one face on record — the ordinary balance reports cover it
        ar = sum((receivable.get(c.pk, Decimal("0.00")) for c in pair["customers"]),
                 Decimal("0.00"))
        ap = sum((payable.get(s.pk, Decimal("0.00")) for s in pair["suppliers"]),
                 Decimal("0.00"))
        if ar == 0 and ap == 0:
            continue
        # Every record on each side is named, so an ambiguous tax number shows
        # as ambiguous instead of silently resolving to whichever sorted first.
        rows.append([
            pair["customers"][0].name,
            ", ".join(c.code for c in pair["customers"]),
            ", ".join(s.code for s in pair["suppliers"]),
            _money(ar), _money(ap), _money(ar - ap),
        ])
    rows.sort(key=lambda r: abs(r[5]), reverse=True)
    total_ar = sum((r[3] for r in rows), Decimal("0.00"))
    total_ap = sum((r[4] for r in rows), Decimal("0.00"))
    total = [_("Total"), "", "", _money(total_ar), _money(total_ap),
             _money(total_ar - total_ap)]
    return columns, rows, total


def _ar_balances(_start, end, _user):
    return _balances_as_of(PartyLedger.PartyType.CUSTOMER, Customer,
                           _("Customer"), end)


def _ap_balances(_start, end, _user):
    return _balances_as_of(PartyLedger.PartyType.SUPPLIER, Supplier,
                           _("Supplier"), end)


def _consignment(_start, _end, _user):
    """Open consignments as of today — ignores the period filter (D73)."""
    columns = [_("Date"), _("Due"), _("Document"), _("Customer"),
               _("Remaining qty"), _("Exposure"), _("Days overdue")]
    rows = []
    today = timezone.localdate()
    issues = (
        Document.objects.filter(
            doc_type__in=[DocType.CONSIGNMENT_ISSUE, DocType.OPENING_CONSIGNMENT],
            status=Document.Status.POSTED,
        )
        .select_related("customer")
        .prefetch_related("lines")
        .order_by("document_date", "pk")
    )
    for issue in issues:
        issued_qty = sum(line.qty_base for line in issue.lines.all())
        issued_value = sum((line.line_net for line in issue.lines.all()), Decimal("0.00"))
        settled = 0
        settlements = DocumentLine.objects.filter(
            document__related_document=issue,
            document__doc_type=DocType.CONSIGNMENT_SETTLEMENT,
            document__status=Document.Status.POSTED,
        )
        for line in settlements:
            settled += line.qty_sold + line.qty_returned + line.qty_expired_unfit
        remaining = max(issued_qty - settled, 0)
        if not remaining:
            continue
        exposure = Decimal("0.00")
        if issued_qty:
            exposure = _money(issued_value * Decimal(remaining) / Decimal(issued_qty))
        overdue = max((today - issue.due_date).days, 0) if issue.due_date else 0
        rows.append([
            _day(issue.document_date), issue.due_date or "", issue.doc_no,
            issue.customer.name, remaining, exposure, overdue,
        ])
    return columns, rows, []


def _vat(start, end, _user):
    columns = [_("Date"), _("Document"), _("Type"), _("Taxable"), _("Exempt"), _("Tax")]
    rows = []
    totals = [Decimal("0.00"), Decimal("0.00"), Decimal("0.00")]
    for doc in _posted_documents(
        [DocType.SALE, DocType.CONSIGNMENT_SETTLEMENT, DocType.CUSTOMER_RETURN],
        start, end,
    ):
        sign = Decimal("-1.00") if doc.doc_type == DocType.CUSTOMER_RETURN else Decimal("1.00")
        taxable = _money(sign * doc.taxable_base)
        exempt = _money(sign * doc.exempt_base)
        tax = _money(sign * doc.tax_total)
        totals[0] += taxable
        totals[1] += exempt
        totals[2] += tax
        rows.append([
            _day(doc.document_date), doc.doc_no, doc.get_doc_type_display(),
            taxable, exempt, tax,
        ])
    return columns, rows, [_("Total"), "", "", _money(totals[0]), _money(totals[1]),
                           _money(totals[2])]


def _withholding_received(start, end, _user):
    columns = [_("Date"), _("Document"), _("Certificate"), _("Amount")]
    rows = []
    total = Decimal("0.00")
    for row in WithholdingLedger.objects.filter(direction=WithholdingLedger.Direction.RECEIVABLE) \
            .select_related("document").order_by("at", "pk"):
        if not _in_range(row.at, start, end):
            continue
        total += row.amount_delta
        rows.append([_day(row.at), row.document.doc_no, row.certificate_no, row.amount_delta])
    return columns, rows, [_("Total"), "", "", _money(total)]


def _withholding_payable(start, end, _user):
    columns = [_("Date"), _("Document"), _("Certificate"), _("Delta")]
    rows = []
    total = Decimal("0.00")
    for row in WithholdingLedger.objects.filter(direction=WithholdingLedger.Direction.PAYABLE) \
            .select_related("document").order_by("at", "pk"):
        if not _in_range(row.at, start, end):
            continue
        total += row.amount_delta
        rows.append([_day(row.at), row.document.doc_no, row.certificate_no, row.amount_delta])
    return columns, rows, [_("Owed in range"), "", "", _money(total)]


def _expenses(start, end, _user):
    columns = [_("Category"), _("Document"), _("Payee"), _("Amount")]
    rows = []
    totals = {}
    for doc in _posted_documents([DocType.EXPENSE], start, end):
        category = doc.expense_category.name if doc.expense_category_id else ""
        totals[category] = totals.get(category, Decimal("0.00")) + doc.grand_total
        rows.append([category, doc.doc_no, doc.payee, doc.grand_total])
    rows.extend([[category, _("Subtotal"), "", _money(total)]
                 for category, total in sorted(totals.items())])
    return columns, rows, []


def _cashbook(start, end, _user):
    columns = [_("Date"), _("Account"), _("Document"), _("Delta")]
    rows = []
    total = Decimal("0.00")
    for row in MoneyLedger.objects.select_related("account", "document").order_by("at", "pk"):
        if not _in_range(row.at, start, end):
            continue
        total += row.amount_delta
        rows.append([_day(row.at), row.account.name, row.document.doc_no, row.amount_delta])
    return columns, rows, [_("Net movement"), "", "", _money(total)]


# Group labels — hub order follows first appearance in REPORTS.
GROUP_STOCK = _("Stock")
GROUP_SALES = _("Sales & profit")
GROUP_PARTIES = _("Receivables & payables")
GROUP_TAX = _("Tax")
GROUP_MONEY = _("Money")

REPORTS = {
    "stock-on-hand": {"title": _("Stock on hand"), "builder": _stock_on_hand,
                      "group": GROUP_STOCK},
    "stock-movement": {"title": _("Stock movement"), "builder": _stock_movement,
                       "group": GROUP_STOCK},
    "expiry": {"title": _("Expiry"), "builder": _expiry, "group": GROUP_STOCK},
    "low-stock": {"title": _("Low stock"), "builder": _low_stock,
                  "group": GROUP_STOCK},
    "valuation": {"title": _("Valuation at lot cost"), "builder": _valuation,
                  "owner_only": True, "group": GROUP_STOCK},
    "consignment": {"title": _("Consignment outstanding"), "builder": _consignment,
                    "open_items": True, "group": GROUP_STOCK},
    "sales-by-brand": {"title": _("Sales by brand, with achieved price"),
                       "builder": _sales_by_brand, "group": GROUP_SALES},
    "sales-by-generic": {"title": _("Sales by generic, with achieved price"),
                         "builder": _sales_by_generic, "group": GROUP_SALES},
    "profit": {"title": _("Profit"), "builder": _profit, "owner_only": True,
               "group": GROUP_SALES},
    "losses": {"title": _("Losses at lot cost"), "builder": _losses,
               "owner_only": True, "group": GROUP_SALES},
    "ar-aging": {"title": _("AR aging"), "builder": _ar_aging, "open_items": True,
                 "group": GROUP_PARTIES},
    "ap-aging": {"title": _("AP aging"), "builder": _ap_aging, "open_items": True,
                 "group": GROUP_PARTIES},
    "ar-balances": {"title": _("AR balances by customer (as of the end date)"),
                    "builder": _ar_balances, "group": GROUP_PARTIES},
    "ap-balances": {"title": _("AP balances by supplier (as of the end date)"),
                    "builder": _ap_balances, "group": GROUP_PARTIES},
    "both-faces": {"title": _("Net position by business (customer and supplier in one)"),
                   "builder": _both_faces, "group": GROUP_PARTIES},
    # Tax reports disappear when the configuration makes them permanently
    # empty (owner request: no dead reports) — flip the setting, they return.
    "vat": {"title": _("VAT summary"), "builder": _vat, "group": GROUP_TAX,
            "enabled": lambda s: s.tax_regime != CompanySettings.TaxRegime.NONE},
    "withholding-received": {
        "title": _("Withholding certificates received"),
        "builder": _withholding_received, "group": GROUP_TAX,
        "enabled": lambda s: s.withholding_on_sales,
    },
    "withholding-payable": {
        "title": _("Withholding withheld/remitted/owed"),
        "builder": _withholding_payable, "group": GROUP_TAX,
        "enabled": lambda s: s.withholding_on_purchases,
    },
    "expenses": {"title": _("Expenses by category"), "builder": _expenses,
                 "group": GROUP_MONEY},
    "cashbook": {"title": _("Cash/bank book"), "builder": _cashbook,
                 "group": GROUP_MONEY},
}


def _report_enabled(config, settings) -> bool:
    enabled = config.get("enabled")
    return enabled is None or enabled(settings)


@login_required
def report_hub(request):
    settings = CompanySettings.load()
    groups: list[dict] = []
    for slug, config in REPORTS.items():
        if not _report_enabled(config, settings):
            continue
        label = config["group"]
        group = next((g for g in groups if g["label"] == label), None)
        if group is None:
            group = {"label": label, "statement": label == GROUP_PARTIES,
                     # D141: the sales report has its own view, so it is
                     # listed here rather than through the slug registry.
                     "sales_lines": label == GROUP_SALES,
                     "entries": []}
            groups.append(group)
        group["entries"].append((slug, config))
    return render(request, "reports/hub.html", {"groups": groups})


@login_required
def report_detail(request, slug):
    config = REPORTS.get(slug)
    if config is None:
        raise Http404
    if not _report_enabled(config, CompanySettings.load()):
        raise Http404
    if config.get("owner_only") and not request.user.is_owner:
        raise PermissionDenied
    # D137: the period this person last chose, restored before it is read.
    restore_filters(request, f"report:{slug}", REPORT_FILTERS)
    period, start, end = _selected_range(request)
    columns, rows, total = config["builder"](start, end, request.user)
    if request.GET.get("format") == "csv":
        return _csv_response(slug, columns, rows, total)
    return render(request, "reports/detail.html", {
        "slug": slug,
        "title": config["title"],
        "columns": columns,
        "rows": rows,
        "total": total,
        "period": period,
        "start": start,
        "end": end,
        "open_items": config.get("open_items", False),
        "today": timezone.localdate(),
    })


def _party_balance(party_type: str, party_id: int) -> Decimal:
    """Net PartyLedger position (reconciliation-grade Python sum, D65)."""
    total = Decimal("0.00")
    rows = PartyLedger.objects.filter(
        party_type=party_type, party_id=party_id,
    ).values_list("amount_delta", flat=True)
    for amount in rows:
        total += amount
    return total


def _open_positions(doc_types, today):
    """(total, overdue, top-3 parties) over posted open documents. Cash
    documents drop out naturally: their auto payment settles them at post."""
    total = Decimal("0.00")
    overdue = Decimal("0.00")
    per_party: dict = {}
    docs = Document.objects.filter(
        doc_type__in=doc_types, status=Document.Status.POSTED,
    ).select_related("customer", "supplier")
    for doc in docs:
        if doc.doc_type in (DocType.SALE, DocType.CONSIGNMENT_SETTLEMENT) \
                and doc.sale_kind != Document.SaleKind.CREDIT:
            continue
        balance = open_balance(doc)
        if balance <= 0:
            continue
        total += balance
        if doc.due_date and doc.due_date < today:
            overdue += balance
        party = doc.customer or doc.supplier
        if party is not None:
            per_party[party] = per_party.get(party, Decimal("0.00")) + balance
    top = sorted(per_party.items(), key=lambda pair: pair[1], reverse=True)[:3]
    return total, overdue, top


SELLABLE_ZONES = (Zone.WAREHOUSE, Zone.CONSIGNED)


def _stock_valuations():
    """(cost by zone, at selling price) for sellable stock. Warehouse and
    consigned cost are kept apart — money on customers' shelves is a
    different risk than money in your own store. Price side uses the same
    D23 rule as sale prefill: maintained price, or latest cost × (1 +
    margin%) for AUTO items."""
    latest = (CostLot.objects.filter(item=OuterRef("pk"))
              .order_by("-received_at", "-pk").values("unit_cost")[:1])
    items = {
        item.pk: item
        for item in Item.objects.annotate(latest_cost=Subquery(latest))
    }
    cost_by_zone = {zone: Decimal("0.00") for zone in SELLABLE_ZONES}
    at_price = Decimal("0.00")
    balances = (
        StockBalance.objects.filter(qty__gt=0, zone__in=SELLABLE_ZONES)
        .select_related("lot")
    )
    for balance in balances:
        cost_by_zone[balance.zone] += _money(
            Decimal(balance.qty) * balance.lot.unit_cost)
        price = _selling_price(items[balance.item_id]) or Decimal("0.00")
        at_price += _money(Decimal(balance.qty) * price)
    return cost_by_zone, at_price


@login_required
def finance(request):
    """Owner's one-screen money position (D79): everything below is a
    read-only aggregation over ledgers the engine already keeps."""
    if not request.user.is_owner:
        raise PermissionDenied
    today = timezone.localdate()

    accounts = [(account, account_balance(account))
                for account in Account.objects.filter(is_active=True).order_by("name")]
    money_total = sum((balance for _a, balance in accounts), Decimal("0.00"))

    ar_total, ar_overdue, top_debtors = _open_positions(AR_TARGET_TYPES, today)
    ap_total, ap_overdue, top_creditors = _open_positions(AP_TARGET_TYPES, today)
    wht_receivable = withholding_balance("RECEIVABLE")
    wht_payable = withholding_balance("PAYABLE")
    net_position = money_total + ar_total - ap_total - wht_payable

    cost_by_zone, stock_price = _stock_valuations()
    stock_warehouse_cost = cost_by_zone[Zone.WAREHOUSE]
    stock_consigned_cost = cost_by_zone[Zone.CONSIGNED]
    stock_cost = stock_warehouse_cost + stock_consigned_cost

    month_start = today.replace(day=1)
    _rows, totals = _sale_line_rows(month_start, today)
    revenue, cogs = totals["revenue"], totals["cogs"]
    expenses = Decimal("0.00")
    for doc in _posted_documents([DocType.EXPENSE], month_start, today):
        expenses += doc.grand_total

    return render(request, "reports/finance.html", {
        "today": today,
        "accounts": accounts,
        "money_total": money_total,
        "ar_total": ar_total,
        "ar_overdue": ar_overdue,
        "top_debtors": top_debtors,
        "ap_total": ap_total,
        "ap_overdue": ap_overdue,
        "top_creditors": top_creditors,
        "wht_receivable": wht_receivable,
        "wht_payable": wht_payable,
        "net_position": net_position,
        "stock_cost": stock_cost,
        "stock_warehouse_cost": stock_warehouse_cost,
        "stock_consigned_cost": stock_consigned_cost,
        "stock_price": stock_price,
        "month": {"revenue": revenue, "cogs": cogs, "gross": revenue - cogs,
                  "expenses": expenses, "net": revenue - cogs - expenses},
    })


@login_required
def statement(request):
    """Party statement for reconciliation (owner request): opening balance,
    every AR/AP movement in the period with a running balance, closing
    balance. Reads PartyLedger only, so cash documents (which never create
    debt) stay out and voids show up as explicit reversal rows."""
    period, start, end = _selected_range(request)
    party_type = request.GET.get("party_type", "customer")
    if party_type not in ("customer", "supplier"):
        party_type = "customer"
    is_customer = party_type == "customer"
    model = Customer if is_customer else Supplier
    try:
        party = model.objects.filter(pk=request.GET.get("party")).first()
    except (TypeError, ValueError):
        party = None

    # A fellow vendor can be both customer and supplier (same TIN, D79):
    # point at the other side's balance so "where do we stand overall" is
    # one glance, while the books stay strictly separate (no netting).
    counterpart = None
    if party is not None and _normalised_tin(party.tin):
        # D127: the old lookup stripped only the *selected* party's tax number
        # and compared it exactly, so a stored " 0012345678 " linked one way
        # and not the other, and `001-2345678` linked neither way. It also
        # required `is_active`, which hid a deactivated supplier that is still
        # owed money — deactivating a record does not settle a debt.
        other_model = Supplier if is_customer else Customer
        wanted = _normalised_tin(party.tin)
        matches = [p for p in other_model.objects.all()
                   if _normalised_tin(p.tin) == wanted]
        # Prefer an active record when the tax number is ambiguous, but never
        # drop the row entirely — `both-faces` names every record on each side.
        matches.sort(key=lambda p: (not p.is_active, p.code))
        other = matches[0] if matches else None
        if other is not None:
            counterpart = {
                "party": other,
                "party_type": "supplier" if is_customer else "customer",
                "balance": _party_balance(
                    PartyLedger.PartyType.SUPPLIER if is_customer
                    else PartyLedger.PartyType.CUSTOMER,
                    other.pk,
                ),
            }

    context = {
        "party_type": party_type,
        "party": party,
        "parties": model.objects.filter(is_active=True).order_by("code"),
        "counterpart": counterpart,
        "period": period,
        "start": start,
        "end": end,
    }
    if party is None:
        return render(request, "reports/statement.html", context)

    ledger_rows = (
        PartyLedger.objects.filter(
            party_type=(PartyLedger.PartyType.CUSTOMER if is_customer
                        else PartyLedger.PartyType.SUPPLIER),
            party_id=party.pk,
        )
        .select_related("document")
        .order_by("document__document_date", "pk")
    )
    opening = Decimal("0.00")
    running = Decimal("0.00")
    entries = []
    for row in ledger_rows:
        day = _day(row.document.document_date)
        if day is None or day > end:
            continue
        if day < start:
            opening += row.amount_delta
            continue
        entries.append({
            "date": day,
            "doc": row.document,
            "type": row.document.get_doc_type_display(),
            "is_reversal": row.is_reversal,
            "delta": row.amount_delta,
            "debit": row.amount_delta if row.amount_delta > 0 else None,
            "credit": -row.amount_delta if row.amount_delta < 0 else None,
            "balance": Decimal("0.00"),  # filled below, after opening is known
        })
    running = opening
    for entry in entries:
        running += entry["delta"]
        entry["balance"] = running
    context.update({"opening": opening, "entries": entries, "closing": running})
    if request.GET.get("format") == "csv":
        return _statement_csv(party, opening, entries, running)
    return render(request, "reports/statement.html", context)


def _statement_csv(party, opening, entries, closing):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="statement.csv"'
    writer = csv.writer(response)
    writer.writerow([_("Statement for"), f"{party.code} — {party.name}"])
    writer.writerow([_("Date"), _("Document"), _("Type"),
                     _("Debit"), _("Credit"), _("Balance")])
    writer.writerow(["", _("Opening balance"), "", "", "", opening])
    for entry in entries:
        writer.writerow([
            entry["date"].isoformat(),
            entry["doc"].doc_no + (f" ({_('void reversal')})" if entry["is_reversal"] else ""),
            entry["type"],
            entry["debit"] if entry["debit"] is not None else "",
            entry["credit"] if entry["credit"] is not None else "",
            entry["balance"],
        ])
    writer.writerow(["", _("Closing balance"), "", "", "", closing])
    return response


def _csv_response(slug, columns, rows, total):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{slug}.csv"'
    writer = csv.writer(response)
    writer.writerow([str(column) for column in columns])
    writer.writerows(rows)
    if total:
        writer.writerow(total)
    return response


# --- D135: party positions, drilling down to the transactions --------------

PARTY_SIDES = {
    "receivable": {
        "party_type": PartyLedger.PartyType.CUSTOMER,
        "model": Customer,
        "other_type": PartyLedger.PartyType.SUPPLIER,
        "other_model": Supplier,
        # D144: the labels are the plain trade words — receivable and
        # payable — not "they owe us". The reports are shown to accountants and
        # to the businesses themselves.
        "title": _("Receivables by customer"),
        "party_label": _("Customer"),
        "other_label": _("Payable"),
        "own_label": _("Receivable"),
        "doc_types": AR_TARGET_TYPES,
        "other_side": "payable",
        "switch_label": _("Show payables"),
    },
    "payable": {
        "party_type": PartyLedger.PartyType.SUPPLIER,
        "model": Supplier,
        "other_type": PartyLedger.PartyType.CUSTOMER,
        "other_model": Customer,
        "title": _("Payables by supplier"),
        "party_label": _("Supplier"),
        "other_label": _("Receivable"),
        "own_label": _("Payable"),
        "doc_types": AP_TARGET_TYPES,
        "other_side": "receivable",
        "switch_label": _("Show receivables"),
    },
}


def _settled_as_of(doc, end):
    """What had actually been paid off this document **by `end`**.

    `open_balance()` (docs/handlers_payments.py) takes no cutoff — it nets every
    posted allocation and every unrefunded return, whenever they happened. That
    is right for "is this still open today" and wrong for "what was owed on the
    30th": a payment made in August would reduce what the report says was owed
    in July, while the party ledger above it correctly would not. The two levels
    then disagree and the reconciling row absorbs the difference instead of
    revealing it. *(Found by gpt-6-astra, 2026-09-11.)*
    """
    settled = Decimal("0.00")
    allocations = (PaymentAllocation.objects
                   .filter(target=doc, payment__status=Document.Status.POSTED)
                   .select_related("payment"))
    for allocation in allocations:
        day = _day(allocation.payment.document_date)
        if day is not None and day <= end:
            settled += allocation.amount
    if doc.doc_type in AR_TARGET_TYPES:
        # R68: a return with no cash refund credits the invoice it came from.
        credits = (Document.objects
                   .filter(related_document=doc, doc_type=DocType.CUSTOMER_RETURN,
                           status=Document.Status.POSTED)
                   .annotate(refund_lines=Count("payment_lines"))
                   .filter(refund_lines=0))
        for credit in credits:
            day = _day(credit.document_date)
            if day is not None and day <= end:
                settled += credit.grand_total
    return min(settled, doc.grand_total)


def _open_documents(doc_types, party_field, end):
    """Posted documents of these types that still owe something **as of `end`**,
    grouped by party id. A cash sale never creates debt, so it is excluded the
    same way aging excludes it (D73)."""
    by_party: dict[int, list] = {}
    docs = (
        Document.objects.filter(doc_type__in=doc_types,
                                status=Document.Status.POSTED)
        .select_related("customer", "supplier")
        .order_by("document_date", "pk")
    )
    for doc in docs:
        if doc.doc_type in (DocType.SALE, DocType.CONSIGNMENT_SETTLEMENT) \
                and doc.sale_kind != Document.SaleKind.CREDIT:
            continue
        day = _day(doc.document_date)
        if day is None or day > end:
            continue
        settled = _settled_as_of(doc, end)
        balance = doc.grand_total - settled
        if balance <= 0:
            continue
        party_id = getattr(doc, f"{party_field}_id")
        if party_id is None:
            continue
        by_party.setdefault(party_id, []).append({
            "document": doc,
            "date": day,
            "due": doc.due_date,
            "original": _money(doc.grand_total),
            "settled": _money(settled),
            "open": _money(balance),
        })
    return by_party


def _by_normalised_name(value: str) -> str:
    """R103: 13 of the client's businesses are on both sides and **none** of
    them carry a matching tax number, so a name fold is the only way to notice
    that a pair exists. It is used to *flag* those for data entry, never to net
    them — netting stays on the tax number, by the owner's decision."""
    return " ".join((value or "").split()).casefold()


@login_required
def party_positions(request, side):
    """D135: one screen that starts at the party, expands to the transactions
    behind the balance, and links to each document.

    **Level one is the ledger balance, not the sum of the open documents.**
    They are different numbers: an owner may post a customer return with no
    sale reference, which credits the party ledger and belongs to no invoice
    (docs/handlers_sales.py). Summing open documents would quietly disagree
    with the statement, the Finance page and this party's own aging. The
    difference is shown on its own row instead.
    """
    config = PARTY_SIDES.get(side)
    if config is None:
        raise Http404
    restore_filters(request, f"positions:{side}", REPORT_FILTERS)
    period, start, end = _selected_range(request)

    balances = _party_totals(config["party_type"], end)
    other_balances = _party_totals(config["other_type"], end)
    parties = {p.pk: p for p in config["model"].objects.filter(pk__in=balances)}
    others = {o.pk: o for o in config["other_model"].objects.all()}

    party_field = "customer" if side == "receivable" else "supplier"
    documents = _open_documents(config["doc_types"], party_field, end)

    # Netting pairs on the tax number only (owner's decision, 2026-09-11).
    others_by_tin: dict[str, list] = {}
    others_by_name: dict[str, list] = {}
    for other in others.values():
        tin = _normalised_tin(other.tin)
        if tin:
            others_by_tin.setdefault(tin, []).append(other)
        others_by_name.setdefault(_by_normalised_name(other.name), []).append(other)

    rows, unpaired = [], []
    for pk, balance in balances.items():
        if balance == 0:
            continue
        party = parties[pk]
        entries = documents.get(pk, [])
        documents_total = sum((e["open"] for e in entries), Decimal("0.00"))

        counterpart = None
        tin = _normalised_tin(party.tin)
        if tin:
            matches = sorted(others_by_tin.get(tin, []),
                             key=lambda o: (not o.is_active, o.code))
            counterpart = matches[0] if matches else None

        counterpart_balance = (other_balances.get(counterpart.pk, Decimal("0.00"))
                               if counterpart else None)
        rows.append({
            "party": party,
            "balance": _money(balance),
            "documents": entries,
            "documents_total": _money(documents_total),
            # Signed deliberately: negative means the ledger holds movements
            # the transaction list cannot show, which is information, not noise.
            "unexplained": _money(balance - documents_total),
            "counterpart": counterpart,
            "counterpart_balance": (_money(counterpart_balance)
                                    if counterpart else None),
            "net": (_money(balance - counterpart_balance)
                    if counterpart else None),
        })

        if counterpart is None:
            # Same business on both sides, no tax number to prove it. Name it
            # so an unfinished data-entry job cannot read as "nobody is here".
            lookalikes = [o for o in others_by_name.get(
                _by_normalised_name(party.name), [])
                if other_balances.get(o.pk, Decimal("0.00")) != 0]
            if lookalikes:
                unpaired.append({
                    "name": party.name,
                    "party": party,
                    "others": lookalikes,
                    "own": _money(balance),
                    "other": _money(sum(
                        (other_balances.get(o.pk, Decimal("0.00"))
                         for o in lookalikes), Decimal("0.00"))),
                })

    rows.sort(key=lambda r: r["balance"], reverse=True)
    total = sum((r["balance"] for r in rows), Decimal("0.00"))
    return render(request, "reports/party_positions.html", {
        "side": side,
        "config": config,
        "rows": rows,
        "unpaired": unpaired,
        "total": _money(total),
        "period": period,
        "start": start,
        "end": end,
    })


# --- D141: the sales report, item named and document reachable -------------

SALES_COLUMNS = [
    (_("Date"), "date"), (_("Document"), "doc_no"), (_("Customer"), "customer"),
    (_("Item"), "code"), (_("Generic"), "generic"), (_("Brand"), "brand"),
    (_("Strength"), "strength"), (_("Qty"), "qty"), (_("Revenue"), "revenue"),
]
SALES_COST_COLUMNS = [(_("COGS"), "cogs"), (_("Profit"), "profit")]
SALES_FILTERS = REPORT_FILTERS + ("doc", "generic", "brand", "group")

EXTRAS_LABEL = _("Other charges and discounts")


def _generic_groups(rows):
    """D144: the same rows, folded one row per generic, lines kept underneath.

    **Money only.** D132 settled that a generic covers several strengths, so
    revenue and cost add across it and quantity does not — 100 tablets of
    500 mg plus 100 of 250 mg is not 200 of anything. `qty` is None on a group
    and the lines inside keep their own.

    R75's charges and discounts belong to no generic, so they form a last
    group of their own rather than being dropped, which would leave the grouped
    view disagreeing with the total above it.
    """
    buckets: dict = {}
    extras = {"label": EXTRAS_LABEL, "lines": [], "revenue": Decimal("0.00"),
              "cogs": Decimal("0.00"), "qty": None, "is_extra": True}
    for row in rows:
        if row["is_extra"]:
            extras["lines"].append(row)
            extras["revenue"] += row["revenue"]
            continue
        key, label = fold_generic(row["generic"])
        bucket = buckets.setdefault(key, {
            "lines": [], "revenue": Decimal("0.00"), "cogs": Decimal("0.00"),
            "names": Counter(), "qty": None, "is_extra": False,
        })
        # Commonest exact spelling wins, alphabetical tie-break, exactly as
        # `_achieved_rows` picks it — so the two reports label a generic the
        # same way as well as splitting it the same way.
        bucket["names"][label] += 1
        bucket["lines"].append(row)
        bucket["revenue"] += row["revenue"]
        bucket["cogs"] += row["cogs"]

    groups = []
    for key in sorted(buckets):
        bucket = buckets[key]
        bucket["label"] = sorted(bucket["names"].items(),
                                 key=lambda kv: (-kv[1], kv[0]))[0][0]
        del bucket["names"]
        bucket["revenue"] = _money(bucket["revenue"])
        bucket["cogs"] = _money(bucket["cogs"])
        bucket["profit"] = _money(bucket["revenue"] - bucket["cogs"])
        groups.append(bucket)
    if extras["lines"]:
        extras["revenue"] = _money(extras["revenue"])
        extras["cogs"] = _money(extras["cogs"])
        extras["profit"] = extras["revenue"]
        groups.append(extras)
    return groups


GROUP_COLUMNS = [(_("Generic"), "label"), (_("Lines"), "count"),
                 (_("Revenue"), "revenue")]


def _sales_csv(rows, totals, show_cost):
    """The same rows the page shows, filters and all. An extras row has no
    item, so its label goes in the Item column — the place a reader looks to
    ask what a row is about."""
    columns = SALES_COLUMNS + (SALES_COST_COLUMNS if show_cost else [])
    response = _csv_start()
    writer = csv.writer(response)
    writer.writerow([str(label) for label, _key in columns])
    for row in rows:
        line = dict(row)
        if row["is_extra"]:
            line["code"] = row["label"]
        writer.writerow(["" if line[key] is None else line[key]
                         for _label, key in columns])
    footer = ["" for _label, _key in columns]
    footer[0] = str(_("Total"))
    footer[8] = totals["revenue"]
    if show_cost:
        footer[9], footer[10] = totals["cogs"], totals["profit"]
    writer.writerow(footer)
    return response


def _groups_csv(groups, totals, show_cost):
    """D144: grouped on screen, grouped in the file. Quantity is absent by
    decision (D132), not by omission, so the column is not there to invite the
    question."""
    columns = GROUP_COLUMNS + (SALES_COST_COLUMNS if show_cost else [])
    response = _csv_start()
    writer = csv.writer(response)
    writer.writerow([str(label) for label, _key in columns])
    for group in groups:
        row = dict(group, count=len(group["lines"]))
        writer.writerow([row[key] for _label, key in columns])
    footer = [str(_("Total")), "", totals["revenue"]]
    if show_cost:
        footer.extend([totals["cogs"], totals["profit"]])
    writer.writerow(footer)
    return response


def _csv_start():
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="sales.csv"'
    return response


@login_required
def sales_report(request):
    """D141. The client's four asks, in one screen:

    *Linkable document* — the row carries the document's pk, so the number is
    an anchor. Reading a report and opening the invoice behind a line was two
    searches; now it is a click.

    *Generic and brand beside the code* — `ITM-0005` named nothing, which is
    what made the money look like it belonged to the invoice rather than to
    the line. Strength rides along, because a strength that appears nowhere on
    screen is the reason it is missing from the catalogue (D134/D136).

    *Per-item money* — already true, unchanged, and now visibly so.

    *Three filters* — document, generic, brand; each a case-insensitive
    fragment, all three combinable, and the total follows what is on screen.
    """
    restore_filters(request, "sales", SALES_FILTERS)
    period, start, end = _selected_range(request)
    filters = {key: request.GET.get(key, "") for key in ("doc", "generic", "brand")}
    rows, totals = _sale_line_rows(start, end, filters)
    show_cost = request.user.is_owner
    grouping = "generic" if request.GET.get("group") == "generic" else "lines"
    groups = _generic_groups(rows) if grouping == "generic" else []
    if request.GET.get("format") == "csv":
        return (_groups_csv(groups, totals, show_cost) if grouping == "generic"
                else _sales_csv(rows, totals, show_cost))
    return render(request, "reports/sales.html", {
        "columns": SALES_COLUMNS + (SALES_COST_COLUMNS if show_cost else []),
        "group_columns": GROUP_COLUMNS + (SALES_COST_COLUMNS if show_cost else []),
        "rows": rows,
        "groups": groups,
        "grouping": grouping,
        "totals": totals,
        "show_cost": show_cost,
        "filters": filters,
        "period": period,
        "start": start,
        "end": end,
    })
