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
                                expiry_entered=FAR_EXPIRY, unit_label="pack")
    post(grn, owner)
    batch = Batch.objects.get()
    sale = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                   customer=customer, sale_kind="CASH")
    DocumentLine.objects.create(document=sale, item=drug, batch=batch,
                                qty_entered=20, unit_price=D("15.00"),
                                unit_label="pack")
    PaymentLine.objects.create(document=sale, account=cash, amount=D("300.00"))
    return post(sale, owner)


def return_draft(actor, sale, drug, qty, zone=Zone.WAREHOUSE, price=None) -> Document:
    doc = Document.objects.create(doc_type=DocType.CUSTOMER_RETURN, created_by=actor,
                                  customer=sale.customer, related_document=sale)
    DocumentLine.objects.create(
        document=doc, item=drug, batch=sale.lines.get().batch, qty_entered=qty,
        unit_price=price if price is not None else D("0.00"),
        target_zone=zone, unit_label="pack",
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
                                target_zone=Zone.WAREHOUSE, unit_label="pack")
    with pytest.raises(PostingError):
        post(cr, employee)


def test_unreferenced_return_needs_entered_cost(owner, sold_sale, drug):
    batch = Batch.objects.get()
    cr = Document.objects.create(doc_type=DocType.CUSTOMER_RETURN,
                                 created_by=owner, customer=sold_sale.customer)
    DocumentLine.objects.create(document=cr, item=drug, batch=batch, qty_entered=1,
                                unit_price=D("15.00"),
                                target_zone=Zone.WAREHOUSE, unit_label="pack")
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
        unit_price=D("15.00"), target_zone=Zone.WAREHOUSE, unit_label="pack",
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
                                unit_label="pack")
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
                                unit_label="pack")
    PaymentLine.objects.create(document=sale2, account=cash, amount=D("1275.00"))
    sale2 = post(sale2, owner)  # 80 left in lot1 + 5 in the return lot
    assert sale2.lines.get().cogs_total == D("850.00")  # all at 10.00
    assert zone_qty(Zone.WAREHOUSE) == 0


# --- R67: a credit note is worth what the invoice charged ------------------

def test_a_return_credits_the_sold_price_not_todays(owner, sold_sale, drug):
    """The entry form prefills the *current* catalogue price (D80) and the
    typed price used to win whenever it was non-empty — so a price rise
    between sale and return refunded more than the customer ever paid."""
    drug.maintained_price = D("25.00")     # price rose after the sale
    drug.save()

    cr = post(return_draft(owner, sold_sale, drug, 5, price=D("25.00")), owner)

    line = cr.lines.get()
    assert line.unit_price == D("15.00")   # what the sale charged
    assert line.line_net == D("75.00")     # 5 x 15, not 5 x 25
    assert cr.grand_total == D("75.00")


def test_a_return_uses_the_sales_frozen_tax_rate(owner, customer, supplier, cash):
    """A rate change between sale and return would otherwise credit a
    different tax than was charged."""
    from core.models import CompanySettings
    settings = CompanySettings.load()
    settings.tax_regime = "VAT"
    settings.vat_rate = D("15.00")
    settings.save()
    item = Item.objects.create(code="STETH", name="Stethoscope", base_unit="unit",
                               is_batch_tracked=False, has_expiry=False,
                               vat_exempt=False, maintained_price=D("100.00"))
    grn = Document.objects.create(doc_type=DocType.RECEIVING, created_by=owner,
                                  supplier=supplier)
    DocumentLine.objects.create(document=grn, item=item, qty_entered=10,
                                unit_cost_entered=D("50.00"), unit_label="unit")
    post(grn, owner)
    sale = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                   customer=customer, sale_kind="CASH")
    DocumentLine.objects.create(document=sale, item=item, qty_entered=2,
                                unit_price=D("100.00"), unit_label="unit")
    PaymentLine.objects.create(document=sale, account=cash, amount=D("230.00"))
    sale = post(sale, owner)
    assert sale.tax_rate_snapshot == D("15.00")

    settings = CompanySettings.load()
    settings.vat_rate = D("20.00")         # the rate changes afterwards
    settings.save()

    cr = Document.objects.create(doc_type=DocType.CUSTOMER_RETURN, created_by=owner,
                                 customer=customer, related_document=sale)
    DocumentLine.objects.create(document=cr, item=item, qty_entered=2,
                                unit_price=D("100.00"), target_zone=Zone.WAREHOUSE,
                                unit_label="unit")
    cr = post(cr, owner)

    assert cr.tax_rate_snapshot == D("15.00")
    assert cr.grand_total == D("230.00")   # exactly what was charged


def test_a_negative_line_discount_is_refused(owner, sold_sale, drug):
    """A negative discount on a credit note is a surcharge for handing goods
    back."""
    cr = return_draft(owner, sold_sale, drug, 5)
    cr.lines.update(line_discount=D("-50.00"))

    with pytest.raises(PostingError, match="negative"):
        post(cr, owner)


# --- R68: the invoice has to know it was credited -------------------------

@pytest.fixture
def credit_sale(owner, customer, supplier, drug):
    """Receive 100 @10, sell 20 @15 on credit — the invoice stays open."""
    grn = Document.objects.create(doc_type=DocType.RECEIVING, created_by=owner,
                                  supplier=supplier)
    DocumentLine.objects.create(document=grn, item=drug, qty_entered=100,
                                unit_cost_entered=D("10.00"), batch_no_entered="B-1",
                                expiry_entered=FAR_EXPIRY, unit_label="pack")
    post(grn, owner)
    sale = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                   customer=customer, sale_kind="CREDIT",
                                   due_date=datetime.date(2026, 12, 31))
    DocumentLine.objects.create(document=sale, item=drug, batch=Batch.objects.get(),
                                qty_entered=20, unit_price=D("15.00"),
                                unit_label="pack")
    return post(sale, owner)


def test_an_unrefunded_return_reduces_the_invoices_open_balance(owner, credit_sale,
                                                                drug):
    """The return credits the customer's account but writes no allocation, so
    the invoice used to read fully open — aging chased money the customer no
    longer owed."""
    from docs.handlers_payments import open_balance

    assert open_balance(credit_sale) == D("300.00")

    post(return_draft(owner, credit_sale, drug, 5), owner)

    credit_sale.refresh_from_db()
    assert open_balance(credit_sale) == D("225.00")   # 300 - 75 credited


def test_a_refunded_return_leaves_the_invoice_owing(owner, credit_sale, drug, cash):
    """Cash went back over the counter, so the invoice itself is still owed."""
    from docs.handlers_payments import open_balance

    cr = return_draft(owner, credit_sale, drug, 5)
    PaymentLine.objects.create(document=cr, account=cash, amount=D("75.00"))
    post(cr, owner)

    credit_sale.refresh_from_db()
    assert open_balance(credit_sale) == D("300.00")


def test_a_referenced_return_of_a_discounted_sale_is_refused(owner, sold_sale, drug):
    """R67: the sale's document discount sits outside the line values a
    referenced return is priced from, so a full return would credit the
    undiscounted total."""
    Document.objects.filter(pk=sold_sale.pk).update(doc_discount=D("20.00"))
    sold_sale.refresh_from_db()

    with pytest.raises(PostingError, match="document discount"):
        post(return_draft(owner, sold_sale, drug, 5), owner)
