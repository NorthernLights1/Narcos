"""P7 stock operations: zone moves, adjustments, stock count snapshot."""

from decimal import Decimal

import pytest
from django.urls import reverse

from core.models import AuditLog
from docs.models import Document, DocType, DocumentLine
from docs.posting import PostingError, post, void
from docs.tests.conftest import make_stocked_item
from stock.models import CostLot, StockBalance, Zone

pytestmark = pytest.mark.django_db

D = Decimal


def zone_qty(lot, zone):
    row = StockBalance.objects.filter(lot=lot, zone=zone).first()
    return row.qty if row else 0


def move_doc(actor, item, lot, source, target, qty):
    doc = Document.objects.create(doc_type=DocType.ZONE_MOVE, created_by=actor)
    DocumentLine.objects.create(
        document=doc, item=item, lot=lot, source_zone=source, target_zone=target,
        unit_label=item.base_unit, factor=1, qty_entered=qty,
    )
    return doc


def test_zone_move_moves_warehouse_stock_to_expired(employee):
    item, lot, _balance = make_stocked_item(qty=10, cost="4.00")
    doc = move_doc(employee, item, lot, Zone.WAREHOUSE, Zone.EXPIRED, 4)
    posted = post(doc, employee)
    assert posted.doc_no == "ZM-000001"
    assert zone_qty(lot, Zone.WAREHOUSE) == 6
    assert zone_qty(lot, Zone.EXPIRED) == 4


def test_zone_move_blocks_consigned_source(employee):
    item, lot, _balance = make_stocked_item(qty=10, cost="4.00")
    doc = move_doc(employee, item, lot, Zone.CONSIGNED, Zone.EXPIRED, 1)
    with pytest.raises(PostingError):
        post(doc, employee)


def test_disposal_is_owner_only(owner, employee):
    item, lot, _balance = make_stocked_item(qty=10, cost="4.00")
    post(move_doc(owner, item, lot, Zone.WAREHOUSE, Zone.EXPIRED, 4), owner)

    blocked = move_doc(employee, item, lot, Zone.EXPIRED, Zone.DISPOSED, 1)
    with pytest.raises(PostingError):
        post(blocked, employee)

    post(move_doc(owner, item, lot, Zone.EXPIRED, Zone.DISPOSED, 2), owner)
    assert zone_qty(lot, Zone.EXPIRED) == 2
    assert zone_qty(lot, Zone.DISPOSED) == 2


def test_owner_adjustment_adds_and_consumes_stock(owner):
    item, _lot, _balance = make_stocked_item(qty=0, cost="4.00")
    add = Document.objects.create(doc_type=DocType.ADJUSTMENT, created_by=owner,
                                  notes="opening correction")
    DocumentLine.objects.create(document=add, item=item, source_zone=Zone.WAREHOUSE,
                                unit_label=item.base_unit, factor=1,
                                qty_entered=1, qty_delta=5,
                                unit_cost_entered=D("9.00"))
    post(add, owner)
    lot = CostLot.objects.order_by("-pk").first()
    assert zone_qty(lot, Zone.WAREHOUSE) == 5
    assert lot.unit_cost == D("9.00")

    sub = Document.objects.create(doc_type=DocType.ADJUSTMENT, created_by=owner,
                                  notes="count correction")
    DocumentLine.objects.create(document=sub, item=item, source_zone=Zone.WAREHOUSE,
                                unit_label=item.base_unit, factor=1,
                                qty_entered=1, qty_delta=-3)
    post(sub, owner)
    assert sum(StockBalance.objects.filter(item=item).values_list("qty", flat=True)) == 2


def test_adjustment_requires_owner(employee):
    item, _lot, _balance = make_stocked_item(qty=10, cost="4.00")
    doc = Document.objects.create(doc_type=DocType.ADJUSTMENT, created_by=employee,
                                  notes="not allowed")
    DocumentLine.objects.create(document=doc, item=item, source_zone=Zone.WAREHOUSE,
                                unit_label=item.base_unit, factor=1,
                                qty_entered=1, qty_delta=-1)
    with pytest.raises(PostingError):
        post(doc, employee)


def test_i16_stock_count_uses_frozen_snapshot_and_warns_on_movement(owner):
    item, lot, _balance = make_stocked_item(qty=10, cost="4.00")
    count = Document.objects.create(doc_type=DocType.STOCK_COUNT, created_by=owner)
    DocumentLine.objects.create(document=count, item=item, lot=lot,
                                source_zone=Zone.WAREHOUSE, unit_label=item.base_unit,
                                factor=1, qty_base=10, qty_entered=7)

    post(move_doc(owner, item, lot, Zone.WAREHOUSE, Zone.EXPIRED, 2), owner)
    assert zone_qty(lot, Zone.WAREHOUSE) == 8

    count = post(count, owner)
    adjustment = Document.objects.get(doc_type=DocType.ADJUSTMENT,
                                      related_document=count)
    assert adjustment.status == Document.Status.POSTED
    assert zone_qty(lot, Zone.WAREHOUSE) == 5  # counted 7 - frozen 10 = -3
    assert AuditLog.objects.filter(action="STOCK_COUNT_MOVEMENT_WARNING").exists()
    with pytest.raises(PostingError):
        void(adjustment, owner, "void source instead")
    void(count, owner, "count error")
    adjustment.refresh_from_db()
    assert adjustment.status == Document.Status.VOIDED
    assert zone_qty(lot, Zone.WAREHOUSE) == 8


def test_stock_count_start_view_freezes_warehouse_balances(client, owner):
    item, lot, _balance = make_stocked_item(qty=6, cost="4.00")
    client.force_login(owner)
    response = client.get(reverse("document_create", args=[DocType.STOCK_COUNT]))
    assert response.status_code == 302
    line = Document.objects.get(doc_type=DocType.STOCK_COUNT).lines.get()
    assert line.item == item
    assert line.lot == lot
    assert line.qty_base == 6
    assert line.qty_entered == 6
