"""D75 inventory pages: per-zone quantities, low/out-of-stock filters, the
item drill-down, and the dashboard low-stock card showing qty vs reorder."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Customer, Item, Supplier
from core.models import User
from docs.models import Document, DocType, DocumentLine
from docs.posting import post
from stock.models import Batch
from stock.views import _stock_status

pytestmark = pytest.mark.django_db

D = Decimal
FAR_EXPIRY = datetime.date(2030, 1, 1)


@pytest.fixture
def owner(db):
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


@pytest.fixture
def customer(db):
    return Customer.objects.create(code="C001", name="Mekelle Hospital PLC")


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(code="S001", name="Addis Pharma")


def make_item(code, name, reorder_level=None):
    return Item.objects.create(code=code, name=name, base_unit="pack",
                               is_batch_tracked=True, has_expiry=True,
                               vat_exempt=True, reorder_level=reorder_level)


def receive(actor, supplier, item, qty=100, cost="10.00"):
    doc = Document.objects.create(doc_type=DocType.RECEIVING, created_by=actor,
                                  supplier=supplier)
    DocumentLine.objects.create(document=doc, item=item, qty_entered=qty,
                                unit_cost_entered=D(cost),
                                batch_no_entered=f"B-{item.code}",
                                expiry_entered=FAR_EXPIRY, unit_label="pack", factor=1)
    return post(doc, actor)


def consign(actor, customer, item, qty):
    doc = Document.objects.create(doc_type=DocType.CONSIGNMENT_ISSUE,
                                  created_by=actor, customer=customer)
    DocumentLine.objects.create(document=doc, item=item,
                                batch=Batch.objects.get(item=item),
                                qty_entered=qty, unit_price=D("15.00"),
                                unit_label="pack", factor=1)
    return post(doc, actor)


def sell(actor, customer, item, qty):
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=actor,
                                  customer=customer, sale_kind="CREDIT",
                                  due_date=datetime.date(2026, 8, 1))
    DocumentLine.objects.create(document=doc, item=item,
                                batch=Batch.objects.get(item=item),
                                qty_entered=qty, unit_price=D("15.00"),
                                unit_label="pack", factor=1)
    return post(doc, actor)


def test_stock_status_rule():
    assert _stock_status(0, None) == "OUT"
    assert _stock_status(0, 5) == "OUT"
    assert _stock_status(5, 5) == "LOW"
    assert _stock_status(6, 5) == "OK"
    assert _stock_status(6, None) == "OK"


def test_inventory_list_shows_per_zone_quantities(client, owner, customer,
                                                  supplier):
    item = make_item("GLV", "Exam Gloves", reorder_level=4)
    receive(owner, supplier, item, qty=100)
    consign(owner, customer, item, qty=40)
    sell(owner, customer, item, qty=20)
    client.force_login(owner)
    response = client.get(reverse("inventory_list"))
    content = response.content.decode()
    assert "Exam Gloves" in content
    row = next(r for r in response.context["rows"] if r["item"].pk == item.pk)
    assert row["warehouse"] == 40   # 100 − 40 consigned − 20 sold
    assert row["consigned"] == 40
    assert row["total"] == 80
    assert row["status"] == "OK"    # 40 > reorder level 4


def test_inventory_low_and_out_filters(client, owner, supplier, customer):
    low = make_item("LOW", "Advil", reorder_level=50)
    receive(owner, supplier, low, qty=5)
    ok = make_item("OK", "Parecetamol", reorder_level=3)
    receive(owner, supplier, ok, qty=100)
    out = make_item("OUT", "Bandage", reorder_level=10)  # never received
    client.force_login(owner)

    rows = client.get(reverse("inventory_list"), {"show": "low"}).context["rows"]
    codes = {row["item"].code for row in rows}
    assert codes == {"LOW", "OUT"}

    rows = client.get(reverse("inventory_list"), {"show": "out"}).context["rows"]
    assert {row["item"].code for row in rows} == {"OUT"}

    rows = client.get(reverse("inventory_list"), {"q": "advil"}).context["rows"]
    assert {row["item"].code for row in rows} == {"LOW"}


def test_inventory_item_page_shows_batches_and_movements(client, owner,
                                                         customer, supplier):
    item = make_item("GLV", "Exam Gloves", reorder_level=4)
    receive(owner, supplier, item, qty=100)
    cn = consign(owner, customer, item, qty=40)
    client.force_login(owner)
    response = client.get(reverse("inventory_item", args=[item.pk]))
    content = response.content.decode()
    assert response.context["warehouse"] == 60
    assert response.context["consigned"] == 40
    assert f"B-{item.code}" in content            # batch row
    assert customer.name in content               # consignment holder
    assert cn.doc_no in content                   # recent movement links the doc


def test_dashboard_low_stock_shows_qty_against_reorder_level(client, owner,
                                                             supplier, customer):
    low = make_item("LOW", "Advil", reorder_level=50)
    receive(owner, supplier, low, qty=5)
    client.force_login(owner)
    content = client.get(reverse("dashboard")).content.decode()
    assert "Advil" in content
    assert "5 in warehouse (reorder at 50)" in content
    assert reverse("inventory_item", args=[low.pk]) in content
