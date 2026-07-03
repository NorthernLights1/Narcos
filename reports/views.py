import csv
import datetime as dt
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _

from catalog.models import Item
from core.ethiopian_calendar import fiscal_year_bounds
from core.models import CompanySettings
from docs.checks import ExpiryStatus, expiry_status
from docs.handlers_payments import open_balance
from docs.models import DocType, Document, DocumentLine
from money.models import MoneyLedger, WithholdingLedger
from stock.models import StockBalance, StockLedger, Zone


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
        .prefetch_related("lines__item", "lines__batch")
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


def _sales_line_rows(start, end, show_cost):
    rows = []
    total_revenue = Decimal("0.00")
    total_cogs = Decimal("0.00")
    for doc in _posted_documents(
        [DocType.SALE, DocType.CONSIGNMENT_SETTLEMENT, DocType.CUSTOMER_RETURN],
        start, end,
    ):
        sign = Decimal("-1.00") if doc.doc_type == DocType.CUSTOMER_RETURN else Decimal("1.00")
        for line in doc.lines.all():
            if doc.doc_type == DocType.CONSIGNMENT_SETTLEMENT:
                qty = line.qty_sold
            else:
                qty = line.qty_base
            revenue = _money(sign * line.line_net)
            cogs = _money(sign * line.cogs_total)
            total_revenue += revenue
            total_cogs += cogs
            row = [
                _day(doc.document_date), doc.doc_no, doc.customer.name,
                line.item.code, int(sign) * qty, revenue,
            ]
            if show_cost:
                row.extend([cogs, _money(revenue - cogs)])
            rows.append(row)
    return rows, total_revenue, total_cogs


def _sales(start, end, user):
    columns = [_("Date"), _("Document"), _("Customer"), _("Item"), _("Qty"),
               _("Revenue")]
    if user.is_owner:
        columns.extend([_("COGS"), _("Profit")])
    rows, revenue, cogs = _sales_line_rows(start, end, user.is_owner)
    total = [_("Total"), "", "", "", "", _money(revenue)]
    if user.is_owner:
        total.extend([_money(cogs), _money(revenue - cogs)])
    return columns, rows, total


def _profit(start, end, _user):
    _rows, revenue, cogs = _sales_line_rows(start, end, True)
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


def _aging(doc_types, party_label, start, end):
    columns = [_("Date"), _("Due"), _("Document"), party_label,
               _("Original"), _("Open"), _("Days")]
    rows = []
    today = timezone.localdate()
    for doc in _posted_documents(doc_types, start, end):
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
            doc.grand_total, balance, max((today - anchor).days, 0),
        ])
    return columns, rows, []


def _ar_aging(start, end, _user):
    return _aging(
        [DocType.SALE, DocType.CONSIGNMENT_SETTLEMENT, DocType.OPENING_AR],
        _("Customer"), start, end,
    )


def _ap_aging(start, end, _user):
    return _aging([DocType.RECEIVING, DocType.OPENING_AP], _("Supplier"), start, end)


def _consignment(start, end, _user):
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
        if not _in_range(issue.document_date, start, end):
            continue
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


REPORTS = {
    "stock-on-hand": {"title": _("Stock on hand"), "builder": _stock_on_hand},
    "stock-movement": {"title": _("Stock movement"), "builder": _stock_movement},
    "expiry": {"title": _("Expiry"), "builder": _expiry},
    "low-stock": {"title": _("Low stock"), "builder": _low_stock},
    "valuation": {"title": _("Valuation at lot cost"), "builder": _valuation,
                  "owner_only": True},
    "sales": {"title": _("Sales by period/customer/item"), "builder": _sales},
    "profit": {"title": _("Profit"), "builder": _profit, "owner_only": True},
    "losses": {"title": _("Losses at lot cost"), "builder": _losses,
               "owner_only": True},
    "ar-aging": {"title": _("AR aging"), "builder": _ar_aging},
    "ap-aging": {"title": _("AP aging"), "builder": _ap_aging},
    "consignment": {"title": _("Consignment outstanding"), "builder": _consignment},
    "vat": {"title": _("VAT summary"), "builder": _vat},
    "withholding-received": {
        "title": _("Withholding certificates received"), "builder": _withholding_received,
    },
    "withholding-payable": {
        "title": _("Withholding withheld/remitted/owed"), "builder": _withholding_payable,
    },
    "expenses": {"title": _("Expenses by category"), "builder": _expenses},
    "cashbook": {"title": _("Cash/bank book"), "builder": _cashbook},
}


@login_required
def report_hub(request):
    return render(request, "reports/hub.html", {"reports": REPORTS})


@login_required
def report_detail(request, slug):
    config = REPORTS.get(slug)
    if config is None:
        raise Http404
    if config.get("owner_only") and not request.user.is_owner:
        raise PermissionDenied
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
    })


def _csv_response(slug, columns, rows, total):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{slug}.csv"'
    writer = csv.writer(response)
    writer.writerow([str(column) for column in columns])
    writer.writerows(rows)
    if total:
        writer.writerow(total)
    return response
