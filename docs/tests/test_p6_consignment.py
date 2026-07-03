"""P6 consignment: frozen values, settlement, and consigned returns."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from catalog.models import Customer, Item, Supplier
from core.models import CompanySettings
from docs.checks import consigned_exposure
from docs.models import Document, DocType, DocumentLine
from docs.posting import PostingError, post
from money.models import PaymentLine, account_balance
from stock.models import Batch, CostLot, StockBalance, Zone

pytestmark = pytest.mark.django_db

D = Decimal
FAR_EXPIRY = datetime.date(2030, 1, 1)


@pytest.fixture
def customer(db):
    return Customer.objects.create(code="C001", name="Mekelle Hospital PLC")


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(code="S001", name="Addis Pharma")


@pytest.fixture
def item(db):
    return Item.objects.create(code="KIT", name="Test kit", base_unit="kit",
                               is_batch_tracked=True, has_expiry=True,
                               vat_exempt=False, maintained_price=D("100.00"))


def receive(actor, supplier, item, qty=10, cost="60.00"):
    doc = Document.objects.create(doc_type=DocType.RECEIVING, created_by=actor,
                                  supplier=supplier)
    DocumentLine.objects.create(document=doc, item=item, qty_entered=qty,
                                unit_cost_entered=D(cost), batch_no_entered="B-1",
                                expiry_entered=FAR_EXPIRY, unit_label="kit", factor=1)
    return post(doc, actor)


def issue(actor, customer, item, qty=5, price="100.00", due_date=None):
    batch = Batch.objects.get()
    doc = Document.objects.create(doc_type=DocType.CONSIGNMENT_ISSUE,
                                  created_by=actor, customer=customer,
                                  due_date=due_date)
    DocumentLine.objects.create(document=doc, item=item, batch=batch,
                                qty_entered=qty, unit_price=D(price),
                                unit_label="kit", factor=1)
    return post(doc, actor)


def qty(zone, lot, customer=None):
    row = StockBalance.objects.filter(
        zone=zone, lot=lot, consignment_customer=customer,
    ).first()
    return row.qty if row else 0


def test_i14_settlement_uses_frozen_issue_price_tax_and_taxability(
        owner, customer, supplier, item):
    settings = CompanySettings.load()
    settings.vat_rate = D("15.00")
    settings.save()
    receive(owner, supplier, item)
    cn = issue(owner, customer, item, qty=5, price="100.00")
    lot = CostLot.objects.get()
    assert cn.doc_no == "CN-000001"
    assert cn.grand_total == D("575.00")
    assert qty(Zone.WAREHOUSE, lot) == 5
    assert qty(Zone.CONSIGNED, lot, customer) == 5
    assert consigned_exposure(customer.pk) == D("500.00")

    item.vat_exempt = True
    item.maintained_price = D("999.00")
    item.save()
    settings.vat_rate = D("20.00")
    settings.save()

    cs = Document.objects.create(doc_type=DocType.CONSIGNMENT_SETTLEMENT,
                                 created_by=owner, customer=customer,
                                 related_document=cn, sale_kind="CREDIT")
    DocumentLine.objects.create(document=cs, item=item, batch=Batch.objects.get(),
                                qty_entered=2, qty_sold=2,
                                unit_label="kit", factor=1)
    cs = post(cs, owner)
    assert cs.doc_no == "CS-000001"
    assert cs.subtotal == D("200.00")
    assert cs.tax_total == D("30.00")  # frozen 15%, not current exempt/20%
    assert cs.grand_total == D("230.00")
    assert cs.party_rows.get().amount_delta == D("230.00")
    assert qty(Zone.CONSIGNED, lot, customer) == 3
    assert consigned_exposure(customer.pk) == D("300.00")


def test_i15_consigned_expired_goods_return_through_settlement(
        owner, customer, supplier, item):
    receive(owner, supplier, item)
    cn = issue(owner, customer, item, qty=4, price="100.00")
    lot = CostLot.objects.get()

    cs = Document.objects.create(doc_type=DocType.CONSIGNMENT_SETTLEMENT,
                                 created_by=owner, customer=customer,
                                 related_document=cn, sale_kind="CREDIT")
    DocumentLine.objects.create(document=cs, item=item, batch=Batch.objects.get(),
                                qty_entered=4, qty_returned=1,
                                qty_expired_unfit=2, target_zone=Zone.EXPIRED,
                                unit_label="kit", factor=1)
    post(cs, owner)
    assert qty(Zone.CONSIGNED, lot, customer) == 1
    assert qty(Zone.WAREHOUSE, lot) == 7
    assert qty(Zone.EXPIRED, lot) == 2


def test_cash_consignment_settlement_moves_money(owner, customer, supplier, item, cash):
    receive(owner, supplier, item)
    cn = issue(owner, customer, item, qty=2, price="100.00")
    cs = Document.objects.create(doc_type=DocType.CONSIGNMENT_SETTLEMENT,
                                 created_by=owner, customer=customer,
                                 related_document=cn, sale_kind="CASH")
    DocumentLine.objects.create(document=cs, item=item, batch=Batch.objects.get(),
                                qty_entered=2, qty_sold=2,
                                unit_label="kit", factor=1)
    PaymentLine.objects.create(document=cs, account=cash, amount=D("230.00"))
    post(cs, owner)
    assert account_balance(cash) == D("230.00")


def test_settlement_cannot_exceed_issue_outstanding(owner, customer, supplier, item):
    receive(owner, supplier, item)
    cn = issue(owner, customer, item, qty=2, price="100.00")
    cs = Document.objects.create(doc_type=DocType.CONSIGNMENT_SETTLEMENT,
                                 created_by=owner, customer=customer,
                                 related_document=cn, sale_kind="CREDIT")
    DocumentLine.objects.create(document=cs, item=item, batch=Batch.objects.get(),
                                qty_entered=3, qty_sold=3,
                                unit_label="kit", factor=1)
    with pytest.raises(PostingError):
        post(cs, owner)


def test_dashboard_lists_due_consignments(client, owner, customer, supplier, item):
    receive(owner, supplier, item)
    cn = issue(owner, customer, item, qty=2, price="100.00",
               due_date=timezone.localdate() + datetime.timedelta(days=5))
    client.force_login(owner)
    response = client.get(reverse("dashboard"))
    content = response.content.decode()
    assert cn.doc_no in content
    assert "Due within 7 days" in content
