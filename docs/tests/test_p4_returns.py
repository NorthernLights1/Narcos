"""I11: customer returns restore stock as a NEW lot at original COGS cost and
carry §5 tax over the returned lines (reports subtract CR docs)."""

import datetime
from decimal import Decimal

import pytest

from catalog.models import Customer, Item, Supplier
from docs.models import Document, DocType, DocumentLine
from docs.posting import PostingError, post
from money.models import PaymentLine, account_balance
from stock.models import Batch, CostLot, StockBalance, Zone

pytestmark = pytest.mark.django_db

D = Decimal
FAR_EXPIRY = datetime.date(2030, 1, 1)


@pytest.fixture
def customer(db):
    return Customer.objects.create(code="C001", name="Selam Pharmacy")


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(code="S001", name="Addis Pharma")


@pytest.fixture
def drug(db):
    return Item.objects.create(code="AMOX", name="Amoxicillin", base_unit="pack",
                               is_batch_tracked=True, has_expiry=True, vat_exempt=True)


@pytest.fixture
def sold_sale(owner, customer, supplier, drug, cash):
    """Receive 100 @10, sell 20 @15 cash. Returns the posted sale."""
    grn = Document.objects.create(doc_type=DocType.RECEIVING, created_by=owner,
                                  supplier=supplier)
    DocumentLine.objects.create(document=grn, item=drug, qty_entered=100,
                                unit_cost_entered=D("10.00"), batch_no_entered="B-1",
                                expiry_entered=FAR_EXPIRY, unit_label="pack", factor=1)
    post(grn, owner)
    batch = Batch.objects.get()
    sale = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                   customer=customer, sale_kind="CASH")
    DocumentLine.objects.create(document=sale, item=drug, batch=batch,
                                qty_entered=20, unit_price=D("15.00"),
                                unit_label="pack", factor=1)
    PaymentLine.objects.create(document=sale, account=cash, amount=D("300.00"))
    return post(sale, owner)


def return_draft(actor, sale, drug, qty, zone=Zone.WAREHOUSE, price=None) -> Document:
    doc = Document.objects.create(doc_type=DocType.CUSTOMER_RETURN, created_by=actor,
                                  customer=sale.customer, related_document=sale)
    DocumentLine.objects.create(
        document=doc, item=drug, batch=sale.lines.get().batch, qty_entered=qty,
        unit_price=price if price is not None else D("0.00"),
        target_zone=zone, unit_label="pack", factor=1,
    )
    return doc


def zone_qty(zone):
    return sum(StockBalance.objects.filter(zone=zone).values_list("qty", flat=True))


def test_i11_return_creates_new_lot_at_original_cogs(owner, sold_sale, drug, cash):
    cr = return_draft(owner, sold_sale, drug, 5)
    PaymentLine.objects.create(document=cr, account=cash, amount=D("75.00"))
    cr = post(cr, owner)
    assert cr.doc_no == "CR-000001"
    # New lot, not a top-up of the old one
    lots = CostLot.objects.order_by("pk")
    assert lots.count() == 2
    new_lot = lots.last()
    assert new_lot.qty_received == 5
    assert new_lot.unit_cost == D("10.00")  # original COGS cost, not sale price
    assert cr.lines.get().cogs_total == D("50.00")
    # Refund paid out
    assert account_balance(cash) == D("225.00")  # 300 − 75
    # Tax over returned lines: exempt → 0; totals carry the sale price
    assert cr.grand_total == D("75.00")
    assert cr.tax_total == D("0.00")


def test_i11_return_price_defaults_from_sale_line(owner, sold_sale, drug):
    cr = return_draft(owner, sold_sale, drug, 5)  # no price given → 15.00 from sale
    cr = post(cr, owner)  # no refund lines → AR credit
    assert cr.grand_total == D("75.00")
    ar = cr.party_rows.get()
    assert ar.amount_delta == D("-75.00")  # AR −


def test_return_to_expired_zone(owner, sold_sale, drug):
    cr = return_draft(owner, sold_sale, drug, 3, zone=Zone.EXPIRED)
    post(cr, owner)
    assert zone_qty(Zone.EXPIRED) == 3
    assert zone_qty(Zone.WAREHOUSE) == 80  # unchanged — went to EXPIRED


def test_cannot_return_more_than_sold(owner, sold_sale, drug):
    cr = return_draft(owner, sold_sale, drug, 21)
    with pytest.raises(PostingError):
        post(cr, owner)


def test_unreferenced_return_is_owner_only(owner, employee, sold_sale, drug):
    batch = Batch.objects.get()
    cr = Document.objects.create(doc_type=DocType.CUSTOMER_RETURN,
                                 created_by=employee, customer=sold_sale.customer)
    DocumentLine.objects.create(document=cr, item=drug, batch=batch, qty_entered=1,
                                unit_price=D("15.00"), unit_cost_entered=D("10.00"),
                                target_zone=Zone.WAREHOUSE, unit_label="pack", factor=1)
    with pytest.raises(PostingError):
        post(cr, employee)


def test_unreferenced_return_needs_entered_cost(owner, sold_sale, drug):
    batch = Batch.objects.get()
    cr = Document.objects.create(doc_type=DocType.CUSTOMER_RETURN,
                                 created_by=owner, customer=sold_sale.customer)
    DocumentLine.objects.create(document=cr, item=drug, batch=batch, qty_entered=1,
                                unit_price=D("15.00"),
                                target_zone=Zone.WAREHOUSE, unit_label="pack", factor=1)
    with pytest.raises(PostingError):
        post(cr, owner)


def test_cumulative_returns_capped_at_sold_qty(owner, sold_sale, drug):
    """Review-gate CRITICAL regression: 20 sold; 15 returned; a second
    15-unit return must be blocked (only 5 remain returnable)."""
    post(return_draft(owner, sold_sale, drug, 15), owner)
    second = return_draft(owner, sold_sale, drug, 15)
    with pytest.raises(PostingError):
        post(second, owner)
    third = return_draft(owner, sold_sale, drug, 5)  # exactly the remainder
    assert post(third, owner).status == Document.Status.POSTED


def test_two_lines_same_item_capped_together(owner, sold_sale, drug):
    """The cap also counts lines within the same return document."""
    cr = return_draft(owner, sold_sale, drug, 15)
    DocumentLine.objects.create(
        document=cr, item=drug, batch=sold_sale.lines.get().batch, qty_entered=15,
        unit_price=D("15.00"), target_zone=Zone.WAREHOUSE, unit_label="pack", factor=1,
    )
    with pytest.raises(PostingError):
        post(cr, owner)


def test_return_of_item_not_on_sale_rejected(owner, sold_sale, customer):
    other = Item.objects.create(code="OTHER", name="Other", base_unit="pack",
                                is_batch_tracked=False, has_expiry=False)
    cr = Document.objects.create(doc_type=DocType.CUSTOMER_RETURN, created_by=owner,
                                 customer=customer, related_document=sold_sale)
    DocumentLine.objects.create(document=cr, item=other, qty_entered=1,
                                unit_price=D("5.00"), target_zone=Zone.WAREHOUSE,
                                unit_label="pack", factor=1)
    with pytest.raises(PostingError):
        post(cr, owner)


def test_returned_goods_resellable_from_new_lot(owner, sold_sale, drug, customer, cash):
    cr = return_draft(owner, sold_sale, drug, 5)
    post(cr, owner)
    batch = Batch.objects.get()
    sale2 = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                    customer=customer, sale_kind="CASH")
    DocumentLine.objects.create(document=sale2, item=drug, batch=batch,
                                qty_entered=85, unit_price=D("15.00"),
                                unit_label="pack", factor=1)
    PaymentLine.objects.create(document=sale2, account=cash, amount=D("1275.00"))
    sale2 = post(sale2, owner)  # 80 left in lot1 + 5 in the return lot
    assert sale2.lines.get().cogs_total == D("850.00")  # all at 10.00
    assert zone_qty(Zone.WAREHOUSE) == 0
