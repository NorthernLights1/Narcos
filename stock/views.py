"""Inventory pages (D75): read-only stock visibility. Quantities come from
StockBalance (the derived cache the posting engine maintains); the low-stock
rule is the dashboard's — warehouse quantity at or below the item's reorder
level. No costs or margins here, so both roles may look (D33)."""

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from catalog.models import Item
from core.models import CompanySettings
from docs.checks import ExpiryStatus, expiry_status
from stock.models import StockBalance, StockLedger, Zone

# Zones that still count as "our stock" — disposed goods are gone for good
HELD_ZONES = (Zone.WAREHOUSE, Zone.CONSIGNED, Zone.EXPIRED, Zone.UNFIT)


def _stock_status(warehouse_qty: int, reorder_level) -> str:
    """OUT/LOW/OK on warehouse stock — sold and consigned goods are already
    outside the warehouse, so both reduce this number."""
    if warehouse_qty <= 0:
        return "OUT"
    if reorder_level is not None and warehouse_qty <= reorder_level:
        return "LOW"
    return "OK"


def _zone_totals_by_item() -> dict[int, dict[str, int]]:
    totals: dict[int, dict[str, int]] = {}
    rows = (
        StockBalance.objects.values("item_id", "zone")
        .annotate(total=Sum("qty"))
        .exclude(total=0)
    )
    for row in rows:
        totals.setdefault(row["item_id"], {})[row["zone"]] = row["total"]
    return totals


@login_required
def inventory_list(request):
    query = request.GET.get("q", "").strip()
    show = request.GET.get("show", "")
    items = Item.objects.filter(is_active=True).order_by("code")
    if query:
        items = items.filter(Q(code__icontains=query) | Q(name__icontains=query))
    totals = _zone_totals_by_item()
    rows = []
    for item in items:
        zones = totals.get(item.pk, {})
        warehouse = zones.get(Zone.WAREHOUSE, 0)
        consigned = zones.get(Zone.CONSIGNED, 0)
        damaged = zones.get(Zone.EXPIRED, 0) + zones.get(Zone.UNFIT, 0)
        status = _stock_status(warehouse, item.reorder_level)
        if show == "low" and status not in ("LOW", "OUT"):
            continue
        if show == "out" and status != "OUT":
            continue
        rows.append({
            "item": item,
            "warehouse": warehouse,
            "consigned": consigned,
            "damaged": damaged,
            "total": warehouse + consigned + damaged,
            "status": status,
        })
    return render(request, "stock/inventory_list.html", {
        "rows": rows,
        "query": query,
        "show": show,
    })


@login_required
def inventory_item(request, pk):
    item = get_object_or_404(Item, pk=pk)
    today = timezone.localdate()
    settings = CompanySettings.load()
    balances = (
        StockBalance.objects.filter(item=item, qty__gt=0)
        .select_related("batch", "consignment_customer")
        .order_by("zone", "batch__expiry_date", "batch__batch_no", "pk")
    )
    batch_rows = []
    zones = {zone: 0 for zone in Zone.values}
    for balance in balances:
        zones[balance.zone] += balance.qty
        expiry = balance.batch.expiry_date if balance.batch else None
        status = (expiry_status(expiry, today, settings.near_expiry_months)
                  if expiry else ExpiryStatus.OK)
        batch_rows.append({"balance": balance, "expiry_status": status})
    warehouse = zones[Zone.WAREHOUSE]
    moves = (
        StockLedger.objects.filter(item=item)
        .select_related("document", "batch", "consignment_customer")
        .order_by("-at", "-pk")[:15]
    )
    return render(request, "stock/inventory_item.html", {
        "item": item,
        "batch_rows": batch_rows,
        "warehouse": warehouse,
        "consigned": zones[Zone.CONSIGNED],
        "expired": zones[Zone.EXPIRED],
        "unfit": zones[Zone.UNFIT],
        "held_total": sum(zones[zone] for zone in HELD_ZONES),
        "status": _stock_status(warehouse, item.reorder_level),
        "moves": moves,
        "expiry_states": ExpiryStatus,
    })
