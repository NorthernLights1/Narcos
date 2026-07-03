"""P8 opening documents and go-live CSV imports."""

import datetime
import io
from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.importers import (
    import_opening_ap,
    import_opening_ar,
    import_opening_cash,
    import_opening_stock,
)
from catalog.models import Account, Customer, Item, Supplier
from docs.handlers_payments import open_balance
from docs.models import Document, DocType, DocumentLine
from docs.posting import post
from money.models import PaymentAllocation, PaymentLine, account_balance
from stock.models import Batch, CostLot, StockBalance, Zone

pytestmark = pytest.mark.django_db

D = Decimal


def as_file(text: str) -> io.BytesIO:
    return io.BytesIO(text.encode("utf-8"))


@pytest.fixture
def customer(db):
    return Customer.objects.create(code="C001", name="Mekelle Hospital")


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(code="S001", name="Addis Pharma")


@pytest.fixture
def drug(db):
    return Item.objects.create(code="AMOX", name="Amoxicillin", base_unit="pack",
                               is_batch_tracked=True, has_expiry=True,
                               vat_exempt=True)


def zone_qty(lot, zone, customer=None):
    row = StockBalance.objects.filter(
        lot=lot, zone=zone, consignment_customer=customer,
    ).first()
    return row.qty if row else 0


def test_opening_stock_import_creates_posted_stock(owner, drug):
    result = import_opening_stock(
        as_file(
            "item_code,batch_no,expiry,qty,unit_cost,document_date\n"
            "AMOX,B-1,2030-01-01,12,9.50,2026-01-15\n"
        ),
        owner,
    )
    assert result.is_clean
    assert result.created == 1
    doc = Document.objects.get(doc_type=DocType.OPENING_STOCK)
    assert doc.status == Document.Status.POSTED
    assert doc.document_date.date() == datetime.date(2026, 1, 15)
    lot = CostLot.objects.get()
    assert lot.unit_cost == D("9.50")
    assert zone_qty(lot, Zone.WAREHOUSE) == 12


def test_dirty_opening_stock_import_posts_nothing(owner, drug):
    result = import_opening_stock(
        as_file(
            "item_code,batch_no,expiry,qty,unit_cost\n"
            "AMOX,B-1,2030-01-01,12,9.50\n"
            "NOPE,B-2,2030-01-01,1,1.00\n"
        ),
        owner,
    )
    assert not result.is_clean
    assert Document.objects.count() == 0
    assert CostLot.objects.count() == 0


def test_opening_ar_keeps_original_date_and_settles_normally(owner, customer, cash):
    result = import_opening_ar(
        as_file(
            "code,amount,document_date,due_date,notes\n"
            "C001,250.00,2025-12-20,2026-01-20,old invoice\n"
        ),
        owner,
    )
    assert result.is_clean
    ar = Document.objects.get(doc_type=DocType.OPENING_AR)
    assert ar.document_date.date() == datetime.date(2025, 12, 20)
    assert ar.due_date == datetime.date(2026, 1, 20)
    assert open_balance(ar) == D("250.00")

    rc = Document.objects.create(doc_type=DocType.CUSTOMER_PAYMENT,
                                 created_by=owner, customer=customer)
    PaymentLine.objects.create(document=rc, account=cash, amount=D("250.00"))
    PaymentAllocation.objects.create(payment=rc, target=ar, amount=D("250.00"))
    post(rc, owner)
    assert open_balance(ar) == D("0.00")
    assert account_balance(cash) == D("250.00")


def test_opening_ap_and_cash_imports(owner, supplier):
    cash = Account.objects.create(name="Cash drawer", type=Account.Type.CASH)
    ap = import_opening_ap(
        as_file("code,amount,document_date\nS001,175.00,2026-01-01\n"),
        owner,
    )
    cash_result = import_opening_cash(
        as_file("account,amount,document_date\nCash drawer,500.00,2026-01-01\n"),
        owner,
    )
    assert ap.is_clean and cash_result.is_clean
    assert Document.objects.filter(doc_type=DocType.OPENING_AP).get().grand_total == D("175.00")
    assert account_balance(cash) == D("500.00")


def test_opening_consignment_can_be_settled(owner, customer, drug):
    op = Document.objects.create(doc_type=DocType.OPENING_CONSIGNMENT,
                                 created_by=owner, customer=customer)
    DocumentLine.objects.create(document=op, item=drug, batch_no_entered="B-1",
                                expiry_entered=datetime.date(2030, 1, 1),
                                unit_label=drug.base_unit, factor=1,
                                qty_entered=5, unit_cost_entered=D("7.00"),
                                unit_price=D("12.00"))
    op = post(op, owner)
    lot = CostLot.objects.get()
    assert zone_qty(lot, Zone.CONSIGNED, customer) == 5

    cs = Document.objects.create(doc_type=DocType.CONSIGNMENT_SETTLEMENT,
                                 created_by=owner, customer=customer,
                                 related_document=op, sale_kind="CREDIT")
    DocumentLine.objects.create(document=cs, item=drug, batch=Batch.objects.get(),
                                unit_label=drug.base_unit, factor=1,
                                qty_entered=2, qty_sold=2)
    post(cs, owner)
    assert zone_qty(lot, Zone.CONSIGNED, customer) == 3
    assert cs.party_rows.get().amount_delta == D("24.00")


def test_opening_import_view_round_trip(client, owner, drug):
    client.force_login(owner)
    upload = io.BytesIO(
        b"item_code,batch_no,expiry,qty,unit_cost\nAMOX,B-1,2030-01-01,2,9.00\n"
    )
    upload.name = "opening-stock.csv"
    response = client.post(reverse("csv_import", args=["opening-stock"]), {"file": upload})
    assert response.status_code == 302
    assert Document.objects.filter(doc_type=DocType.OPENING_STOCK,
                                   status=Document.Status.POSTED).exists()
