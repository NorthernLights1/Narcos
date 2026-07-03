"""P3: Receiving (§7.1) + supplier return (§7.7). Acceptance: I7 (frozen lot
costs), D21 bonus math, re-receipt same batch new price → two lots, D5 void."""

import datetime
from decimal import Decimal

import pytest

from catalog.models import Item, Supplier
from docs.models import Document, DocType, DocumentLine
from docs.posting import PostingError, post, void
from money.models import PaymentLine, account_balance
from stock.models import Batch, CostLot, StockBalance, Zone

pytestmark = pytest.mark.django_db

EXPIRY = datetime.date(2028, 6, 30)


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(code="S001", name="Addis Pharma")


@pytest.fixture
def drug(db):
    return Item.objects.create(code="AMOX-500", name="Amoxicillin",
                               base_unit="pack", is_batch_tracked=True, has_expiry=True)


@pytest.fixture
def equipment(db):
    return Item.objects.create(code="STETH", name="Stethoscope",
                               base_unit="unit", is_batch_tracked=False, has_expiry=False)


def receiving(actor, supplier, *line_specs) -> Document:
    """line_specs: dicts with item, qty, cost, plus optional free/batch_no/expiry/factor."""
    doc = Document.objects.create(doc_type=DocType.RECEIVING, created_by=actor,
                                  supplier=supplier)
    for spec in line_specs:
        DocumentLine.objects.create(
            document=doc, item=spec["item"], qty_entered=spec["qty"],
            unit_cost_entered=Decimal(spec["cost"]), free_qty=spec.get("free", 0),
            batch_no_entered=spec.get("batch_no", ""),
            expiry_entered=spec.get("expiry"),
            unit_label=spec.get("unit", spec["item"].base_unit),
            factor=spec.get("factor", 1),
        )
    return doc


def warehouse_qty(lot) -> int:
    row = StockBalance.objects.filter(lot=lot, zone=Zone.WAREHOUSE).first()
    return row.qty if row else 0


# --- Basic receiving ---


def test_receiving_creates_batch_lot_stock_and_ap(owner, supplier, drug):
    doc = post(receiving(owner, supplier,
                         {"item": drug, "qty": 100, "cost": "10.00",
                          "batch_no": "B-1", "expiry": EXPIRY}), owner)
    assert doc.doc_no == "GRN-000001"
    batch = Batch.objects.get(item=drug, batch_no="B-1")
    assert batch.expiry_date == EXPIRY
    lot = CostLot.objects.get()
    assert lot.qty_received == 100 and lot.unit_cost == Decimal("10.00")
    assert warehouse_qty(lot) == 100
    ap = doc.party_rows.get()
    assert ap.party_type == "SUPPLIER" and ap.amount_delta == Decimal("1000.00")


def test_receiving_cash_now_moves_money_without_ap(owner, supplier, drug, cash):
    doc = receiving(owner, supplier,
                    {"item": drug, "qty": 10, "cost": "10.00",
                     "batch_no": "B-1", "expiry": EXPIRY})
    PaymentLine.objects.create(document=doc, account=cash, amount=Decimal("100.00"))
    doc = post(doc, owner)
    payment = Document.objects.get(doc_type=DocType.SUPPLIER_PAYMENT,
                                   related_document=doc)
    assert payment.doc_no == "PV-000001"
    assert doc.money_rows.count() == 0
    assert account_balance(cash) == Decimal("-100.00")
    assert doc.party_rows.count() == 0


def test_non_batch_item_receives_without_batch(owner, supplier, equipment):
    post(receiving(owner, supplier, {"item": equipment, "qty": 5, "cost": "900.00"}), owner)
    lot = CostLot.objects.get()
    assert lot.batch is None
    assert warehouse_qty(lot) == 5


def test_unit_conversion_lands_in_base_units(owner, supplier, drug):
    # 5 cartons of 12 at 120.00/carton → 60 base at 10.00
    post(receiving(owner, supplier,
                   {"item": drug, "qty": 5, "cost": "120.00", "unit": "carton",
                    "factor": 12, "batch_no": "B-1", "expiry": EXPIRY}), owner)
    lot = CostLot.objects.get()
    assert lot.qty_received == 60
    assert lot.unit_cost == Decimal("10.00")


# --- D21 bonus goods ---


def test_bonus_goods_lower_unit_cost(owner, supplier, drug):
    # 100 paid at 11.00 + 10 free → 1100.00 / 110 = 10.00
    post(receiving(owner, supplier,
                   {"item": drug, "qty": 100, "cost": "11.00", "free": 10,
                    "batch_no": "B-1", "expiry": EXPIRY}), owner)
    lot = CostLot.objects.get()
    assert lot.qty_received == 110
    assert lot.unit_cost == Decimal("10.00")
    assert warehouse_qty(lot) == 110


def test_free_only_line_costs_zero(owner, supplier, drug):
    post(receiving(owner, supplier,
                   {"item": drug, "qty": 0, "cost": "0.00", "free": 10,
                    "batch_no": "B-1", "expiry": EXPIRY}), owner)
    lot = CostLot.objects.get()
    assert lot.unit_cost == Decimal("0.00")
    assert lot.qty_received == 10


# --- I7: frozen lot costs, two lots on re-receipt ---


def test_i7_rereceipt_same_batch_new_price_makes_second_lot(owner, supplier, drug):
    post(receiving(owner, supplier,
                   {"item": drug, "qty": 100, "cost": "10.00",
                    "batch_no": "B-1", "expiry": EXPIRY}), owner)
    post(receiving(owner, supplier,
                   {"item": drug, "qty": 50, "cost": "12.00",
                    "batch_no": "B-1", "expiry": EXPIRY}), owner)
    assert Batch.objects.filter(item=drug).count() == 1  # one batch (D40)
    lots = list(CostLot.objects.order_by("received_at", "pk"))
    assert len(lots) == 2  # two cost lots (D1)
    assert lots[0].unit_cost == Decimal("10.00")  # old lot untouched (I7)
    assert lots[1].unit_cost == Decimal("12.00")


def test_i7_lot_cost_cannot_be_edited(owner, supplier, drug):
    post(receiving(owner, supplier,
                   {"item": drug, "qty": 10, "cost": "10.00",
                    "batch_no": "B-1", "expiry": EXPIRY}), owner)
    lot = CostLot.objects.get()
    lot.unit_cost = Decimal("1.00")
    with pytest.raises(NotImplementedError):
        lot.save()


def test_same_batch_different_expiry_rejected(owner, supplier, drug):
    post(receiving(owner, supplier,
                   {"item": drug, "qty": 10, "cost": "10.00",
                    "batch_no": "B-1", "expiry": EXPIRY}), owner)
    clash = receiving(owner, supplier,
                      {"item": drug, "qty": 10, "cost": "10.00",
                       "batch_no": "B-1", "expiry": datetime.date(2029, 1, 1)})
    with pytest.raises(PostingError):
        post(clash, owner)


# --- Validation rules (D22/D29/D42) ---


def test_batch_required_for_tracked_item(owner, supplier, drug):
    doc = receiving(owner, supplier, {"item": drug, "qty": 10, "cost": "10.00"})
    with pytest.raises(PostingError):
        post(doc, owner)


def test_expiry_required_when_item_has_expiry(owner, supplier, drug):
    doc = receiving(owner, supplier,
                    {"item": drug, "qty": 10, "cost": "10.00", "batch_no": "B-1"})
    with pytest.raises(PostingError):
        post(doc, owner)


def test_batch_forbidden_on_untracked_item(owner, supplier, equipment):
    doc = receiving(owner, supplier,
                    {"item": equipment, "qty": 1, "cost": "5.00", "batch_no": "X"})
    with pytest.raises(PostingError):
        post(doc, owner)


# --- D5 void rules ---


def test_void_untouched_receiving_restores_everything(owner, supplier, drug):
    doc = post(receiving(owner, supplier,
                         {"item": drug, "qty": 100, "cost": "10.00",
                          "batch_no": "B-1", "expiry": EXPIRY}), owner)
    void(doc, owner, "entry error")
    lot = CostLot.objects.get()
    assert warehouse_qty(lot) == 0
    ap_total = sum((r.amount_delta for r in doc.party_rows.all()), Decimal("0.00"))
    assert ap_total == Decimal("0.00")  # I2 on AP


def test_void_blocked_after_goods_moved(owner, supplier, drug):
    """D5: consume part of the received lot, then try to void the receiving."""
    doc = post(receiving(owner, supplier,
                         {"item": drug, "qty": 100, "cost": "10.00",
                          "batch_no": "B-1", "expiry": EXPIRY}), owner)
    lot = CostLot.objects.get()
    # Return 10 to the supplier — consumes part of the lot
    sr = Document.objects.create(doc_type=DocType.SUPPLIER_RETURN,
                                 created_by=owner, supplier=supplier)
    DocumentLine.objects.create(document=sr, item=drug, lot=lot, qty_entered=10,
                                unit_label="pack", factor=1)
    post(sr, owner)
    with pytest.raises(PostingError):
        void(doc, owner, "should be blocked")


# --- Supplier return (§7.7) ---


def test_supplier_return_reduces_stock_and_ap(owner, supplier, drug):
    post(receiving(owner, supplier,
                   {"item": drug, "qty": 100, "cost": "10.00",
                    "batch_no": "B-1", "expiry": EXPIRY}), owner)
    lot = CostLot.objects.get()
    sr = Document.objects.create(doc_type=DocType.SUPPLIER_RETURN,
                                 created_by=owner, supplier=supplier)
    DocumentLine.objects.create(document=sr, item=drug, lot=lot, qty_entered=20,
                                unit_label="pack", factor=1)
    sr = post(sr, owner)
    assert sr.doc_no == "SR-000001"
    assert warehouse_qty(lot) == 80
    assert sr.grand_total == Decimal("200.00")  # 20 × frozen 10.00
    ap = sum((r.amount_delta for r in sr.party_rows.all()), Decimal("0.00"))
    assert ap == Decimal("-200.00")
    consumption = sr.lines.get().lot_consumptions.get()
    assert consumption.qty == 20 and consumption.unit_cost == Decimal("10.00")


def test_supplier_return_with_cash_refund(owner, supplier, drug, cash):
    post(receiving(owner, supplier,
                   {"item": drug, "qty": 50, "cost": "10.00",
                    "batch_no": "B-1", "expiry": EXPIRY}), owner)
    lot = CostLot.objects.get()
    sr = Document.objects.create(doc_type=DocType.SUPPLIER_RETURN,
                                 created_by=owner, supplier=supplier)
    DocumentLine.objects.create(document=sr, item=drug, lot=lot, qty_entered=5,
                                unit_label="pack", factor=1)
    PaymentLine.objects.create(document=sr, account=cash, amount=Decimal("50.00"))
    post(sr, owner)
    assert account_balance(cash) == Decimal("50.00")  # refund received
    assert sr.party_rows.count() == 0  # refund path, not AP


def test_supplier_return_cannot_exceed_lot_balance(owner, supplier, drug):
    post(receiving(owner, supplier,
                   {"item": drug, "qty": 30, "cost": "10.00",
                    "batch_no": "B-1", "expiry": EXPIRY}), owner)
    lot = CostLot.objects.get()
    sr = Document.objects.create(doc_type=DocType.SUPPLIER_RETURN,
                                 created_by=owner, supplier=supplier)
    DocumentLine.objects.create(document=sr, item=drug, lot=lot, qty_entered=31,
                                unit_label="pack", factor=1)
    with pytest.raises(PostingError):
        post(sr, owner)


def test_supplier_return_wrong_lot_item_rejected(owner, supplier, drug, equipment):
    post(receiving(owner, supplier,
                   {"item": drug, "qty": 10, "cost": "10.00",
                    "batch_no": "B-1", "expiry": EXPIRY}), owner)
    lot = CostLot.objects.get()
    sr = Document.objects.create(doc_type=DocType.SUPPLIER_RETURN,
                                 created_by=owner, supplier=supplier)
    DocumentLine.objects.create(document=sr, item=equipment, lot=lot, qty_entered=1,
                                unit_label="unit", factor=1)
    with pytest.raises(PostingError):
        post(sr, owner)
