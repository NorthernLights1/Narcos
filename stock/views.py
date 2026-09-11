"""Inventory pages (D75): read-only stock visibility. Quantities come from
StockBalance (the derived cache the posting engine maintains); the low-stock
rule is the dashboard's — warehouse quantity at or below the item's reorder
level. No costs or margins here, so both roles may look (D33)."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q, Sum
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from catalog.models import Item
from core.audit import log_event
from core.models import CompanySettings
from core.preferences import INVENTORY_FILTERS, restore_filters
from docs.checks import ExpiryStatus, expiry_status
from docs.models import DocType, Document
from stock.forms import BatchExpiryForm
from stock.models import Batch, StockBalance, StockLedger, Zone

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
    # D137: restored before anything reads the querystring, or the
    # remembered value arrives too late to be used.
    restore_filters(request, "inventory", INVENTORY_FILTERS)
    query = request.GET.get("q", "").strip()
    show = request.GET.get("show", "")
    items = Item.objects.filter(is_active=True).order_by("code")
    if query:
        # R105: the generic is how this trade names a thing — `Item.__str__`
        # leads with it (R48) and Master already searches it. Leaving it out
        # here made every brand-named item ("Folly" for a catheter) look absent
        # on the one screen that answers "how many have I got".
        # D134: strength joins them. It was printed on every document and shown
        # on no screen, so two items differing only by strength could not be
        # told apart here at all.
        items = items.filter(Q(code__icontains=query)
                             | Q(name__icontains=query)
                             | Q(generic_name__icontains=query)
                             | Q(strength__icontains=query))
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


def _iso(value) -> str:
    """One encoder for both sides of the reviewed-basis comparison.

    The template renders a missing date as an empty string, so comparing
    against `str(None)` — "None" — could never match, and a batch with no
    expiry yet would be sent round the review loop forever.
    """
    return value.isoformat() if value else ""


def _refresh() -> HttpResponse:
    """A successful change reloads the page. The batch table is ordered by
    expiry, carries expiry badges, and one batch can appear on several rows at
    once — swapping a single cell would leave the rest of the page lying."""
    response = HttpResponse(status=204)
    response["HX-Refresh"] = "true"
    return response


def _batch_impact(batch: Batch, current_expiry, new_expiry, today, settings) -> dict:
    """R62/D121: everything the owner should see before changing an expiry.

    One manufacturer batch has one real expiry, so the Batch row is shared by
    every document that ever received or moved it — the change is not scoped
    to whichever page it was started from. This gathers what else it lands on
    and, when a new date is on the table, whether that date flips the stock
    between sellable and expired (D46).
    """
    documents = list(
        Document.objects.filter(lines__batch=batch)
        .exclude(status=Document.Status.DRAFT)   # voided ones still cite it
        .distinct().order_by("document_date", "pk")
    )
    # Only stock we still hold, and only the warehouse can be sold from —
    # DISPOSED is gone for good and EXPIRED/UNFIT need a zone move first.
    on_hand = list(
        StockBalance.objects.filter(batch=batch, qty__gt=0,
                                    zone__in=HELD_ZONES)
        .values("zone").annotate(total=Sum("qty")).order_by("zone")
    )
    warehouse_qty = sum(row["total"] for row in on_hand
                        if row["zone"] == Zone.WAREHOUSE)
    # `current_expiry` is passed in rather than read off the instance: a bound
    # ModelForm has already written the proposed date onto `batch` by the time
    # this runs, so the instance no longer knows what it is replacing.
    months = settings.near_expiry_months
    now_status = expiry_status(current_expiry, today, months) \
        if current_expiry else None
    next_status = expiry_status(new_expiry, today, months) if new_expiry else None
    zone_labels = dict(Zone.choices)
    return {
        "documents": documents,
        "on_hand": [{"zone": zone_labels.get(row["zone"], row["zone"]),
                     "total": row["total"]} for row in on_hand],
        "held_total": sum(row["total"] for row in on_hand),
        "warehouse_qty": warehouse_qty,
        "now_status": now_status,
        "next_status": next_status,
        # Said out loud rather than left to be inferred from two dates — and
        # only about warehouse stock, because that is the only stock a sale
        # can consume. Goods sitting in EXPIRED or UNFIT stay put either way.
        "becomes_sellable": (warehouse_qty > 0
                             and now_status == ExpiryStatus.EXPIRED
                             and next_status is not None
                             and next_status != ExpiryStatus.EXPIRED),
        "becomes_expired": (warehouse_qty > 0
                            and next_status == ExpiryStatus.EXPIRED
                            and now_status != ExpiryStatus.EXPIRED),
        # Pulling a date backwards can reveal that this batch left the
        # building after the date it really expired. That is a recall
        # question, not a bookkeeping one, so it is named rather than implied.
        "issued_after_expiry": _issued_after(documents, new_expiry),
    }


def _issued_after(documents, new_expiry) -> list:
    """Posted sales and consignment issues dated after the proposed expiry."""
    if new_expiry is None:
        return []
    out_types = (DocType.SALE, DocType.CONSIGNMENT_ISSUE)
    late = []
    for doc in documents:
        if doc.doc_type not in out_types or doc.document_date is None:
            continue
        if doc.status != Document.Status.POSTED:
            continue
        if timezone.localtime(doc.document_date).date() > new_expiry:
            late.append(doc)
    return late


def _expiry_context(batch: Batch, current_expiry, new_expiry=None) -> dict:
    return {
        "batch": batch,
        "current_expiry": current_expiry,
        "today": timezone.localdate(),
        "impact": _batch_impact(batch, current_expiry, new_expiry,
                                timezone.localdate(), CompanySettings.load()),
    }


@login_required
def batch_expiry_edit(request, pk):
    """R62/D121: correct a mistyped expiry without voiding the document.

    Void-and-repost is refused once any of the stock has been sold, so a typo
    caught late used to be uncorrectable through the app entirely — the only
    route was editing the database by hand, unaudited. This is the route the
    R62 note asked for if it were ever revisited: owner-only, a reason
    required, and the impact shown before the change lands.

    A successful save asks htmx to reload the page rather than swapping the
    one cell. The batch table is ordered by expiry and carries expiry badges,
    and a batch can appear on several rows at once (one per zone) — refreshing
    is the only way every one of them tells the truth afterwards.
    """
    if not request.user.is_owner:
        raise PermissionDenied
    batch = get_object_or_404(Batch.objects.select_related("item"), pk=pk)
    if not batch.item.has_expiry:
        raise Http404          # nothing to correct; the field is never set

    if request.method == "POST":
        before = batch.expiry_date          # read before the form binds
        form = BatchExpiryForm(request.POST, instance=batch)
        if not form.is_valid():
            # 200, not 400: htmx 2.0.4 defaults `[45]..` to swap:false, so a
            # 400 renders nothing at all and the error never reaches the user.
            return render(request, "stock/_batch_expiry_edit.html",
                          _expiry_context(batch, before) | {"form": form})
        proposed = form.cleaned_data["expiry_date"]
        today = timezone.localdate()
        # The review step is what the R62 note asked for: only a proposed date
        # can say whether the goods stop selling or start again. All three
        # inputs to those warnings are echoed back — the date proposed, the
        # date it was replacing, and the day it was judged on — and any of them
        # differing means what was on screen no longer describes what would
        # happen, so it goes round again. Not tamper-proofing: the owner is
        # allowed to make this change, so signing would defend the review
        # against the only person entitled to skip it.
        stale = (request.POST.get("reviewed_expiry", "") != _iso(proposed)
                 or request.POST.get("reviewed_from", "") != _iso(before)
                 or request.POST.get("reviewed_on", "") != _iso(today))
        if not request.POST.get("confirm") or stale:
            return render(request, "stock/_batch_expiry_edit.html",
                          _expiry_context(batch, before, proposed)
                          | {"form": form, "confirming": True})
        with transaction.atomic():
            # Lock the row so two owners cannot both read the old date and
            # write different ones, and so the change and the audit row that
            # justifies it land together or not at all.
            locked = Batch.objects.select_for_update().get(pk=batch.pk)
            before = locked.expiry_date
            # Re-read the day too: EXPIRED and NEAR are relative to today, so
            # a request that waited on this lock across midnight was reviewed
            # against a verdict that has since changed.
            today = timezone.localdate()
            if before == proposed:
                # Already what was asked for — by this request's own retry, or
                # by whoever got the lock first. An audit row reading "from X
                # to X" is noise that buries the real corrections. Checked
                # here, under the lock, not before it.
                return _refresh()
            if (_iso(before) != request.POST.get("reviewed_from", "")
                    or _iso(today) != request.POST.get("reviewed_on", "")):
                # It moved between the review and the lock, or the day did.
                # Either way the warnings on screen described something else.
                return render(request, "stock/_batch_expiry_edit.html",
                              _expiry_context(locked, before, proposed)
                              | {"form": form, "confirming": True})
            impact = _batch_impact(locked, before, proposed, today,
                                   CompanySettings.load())
            locked.expiry_date = proposed
            locked.save(update_fields=["expiry_date"])
            log_event(request.user, "BATCH_EXPIRY_UPDATE", "Batch", locked.pk, {
                "item": batch.item.code,
                "batch_no": locked.batch_no,
                "from": str(before),
                "to": str(proposed),
                "reason": form.cleaned_data["reason"],
                "documents": ", ".join(d.doc_no for d in impact["documents"]
                                       if d.doc_no),
                "issued_after_expiry": ", ".join(
                    d.doc_no for d in impact["issued_after_expiry"] if d.doc_no),
            })
        return _refresh()

    if request.GET.get("display"):          # Cancel: put the value back
        return render(request, "stock/_batch_expiry_value.html", {"batch": batch})
    return render(request, "stock/_batch_expiry_edit.html",
                  _expiry_context(batch, batch.expiry_date)
                  | {"form": BatchExpiryForm(instance=batch)})
