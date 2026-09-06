"""Finance overview (owner-only): every money number the engine already
tracks, on one screen — cash/bank, AR/AP with overdue slices, withholding
positions, stock at cost and at price, month-to-date P&L, net position."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from catalog.models import Account, Customer, Item, Supplier
from core.models import User
from docs.models import Document, DocType, DocumentLine
from docs.posting import post
from money.models import PaymentLine
from stock.models import Batch

pytestmark = pytest.mark.django_db

D = Decimal
FAR_EXPIRY = datetime.date(2030, 1, 1)


@pytest.fixture
def owner():
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


@pytest.fixture
def employee():
    return User.objects.create_user("staff", password="pw", role=User.Role.EMPLOYEE)


@pytest.fixture
def scenario(owner):
    """Receiving 10 packs @10 on credit due yesterday (AP 100, overdue);
    credit sale 2 @15 (AR 30); cash sale 1 @15 (drawer 15)."""
    cash = Account.objects.create(name="Cash drawer", type=Account.Type.CASH)
    customer = Customer.objects.create(code="C001", name="Selam Pharmacy")
    supplier = Supplier.objects.create(code="S001", name="Addis Pharma")
    item = Item.objects.create(
        code="AMOX", name="Amoxicillin", base_unit="pack",
        is_batch_tracked=True, has_expiry=True, vat_exempt=True,
        maintained_price=D("15.00"),
    )
    grn = Document.objects.create(
        doc_type=DocType.RECEIVING, created_by=owner, supplier=supplier,
        due_date=timezone.localdate() - datetime.timedelta(days=1),
    )
    DocumentLine.objects.create(
        document=grn, item=item, qty_entered=10, unit_cost_entered=D("10.00"),
        batch_no_entered="B-1", expiry_entered=FAR_EXPIRY,
        unit_label=item.base_unit, factor=1,
    )
    post(grn, owner)
    batch = Batch.objects.get(item=item)

    credit = Document.objects.create(
        doc_type=DocType.SALE, created_by=owner, customer=customer,
        sale_kind=Document.SaleKind.CREDIT,
        due_date=timezone.localdate() + datetime.timedelta(days=30),
    )
    DocumentLine.objects.create(
        document=credit, item=item, batch=batch, qty_entered=2,
        unit_price=D("15.00"), unit_label=item.base_unit, factor=1,
    )
    post(credit, owner)

    cash_sale = Document.objects.create(
        doc_type=DocType.SALE, created_by=owner, customer=customer,
        sale_kind=Document.SaleKind.CASH,
    )
    DocumentLine.objects.create(
        document=cash_sale, item=item, batch=batch, qty_entered=1,
        unit_price=D("15.00"), unit_label=item.base_unit, factor=1,
    )
    PaymentLine.objects.create(document=cash_sale, account=cash, amount=D("15.00"))
    post(cash_sale, owner)
    return {"customer": customer, "supplier": supplier, "item": item}


def test_finance_owner_only(client, owner, employee):
    client.force_login(employee)
    assert client.get(reverse("finance")).status_code == 403
    client.force_login(owner)
    assert client.get(reverse("finance")).status_code == 200


def test_finance_positions(client, owner, scenario):
    client.force_login(owner)
    context = client.get(reverse("finance")).context
    assert context["money_total"] == D("15.00")
    assert context["ar_total"] == D("30.00")
    assert context["ar_overdue"] == D("0.00")
    assert context["ap_total"] == D("100.00")
    assert context["ap_overdue"] == D("100.00")
    # net = money + AR − AP − withholding payable
    assert context["net_position"] == D("-55.00")


def test_finance_stock_valuations(client, owner, scenario):
    client.force_login(owner)
    context = client.get(reverse("finance")).context
    # 7 packs left: at cost 7×10, at selling price 7×15
    assert context["stock_cost"] == D("70.00")
    assert context["stock_price"] == D("105.00")
    assert context["stock_warehouse_cost"] == D("70.00")
    assert context["stock_consigned_cost"] == D("0.00")


def test_finance_splits_consigned_stock(client, owner, scenario):
    """Money on customers' shelves is shown apart from warehouse money."""
    item = scenario["item"]
    issue = Document.objects.create(
        doc_type=DocType.CONSIGNMENT_ISSUE, created_by=owner,
        customer=scenario["customer"],
    )
    DocumentLine.objects.create(
        document=issue, item=item, batch=Batch.objects.get(item=item),
        qty_entered=3, unit_price=D("15.00"),
        unit_label=item.base_unit, factor=1,
    )
    post(issue, owner)
    client.force_login(owner)
    context = client.get(reverse("finance")).context
    assert context["stock_warehouse_cost"] == D("40.00")   # 4 packs left
    assert context["stock_consigned_cost"] == D("30.00")   # 3 packs out
    assert context["stock_cost"] == D("70.00")             # total unchanged
    assert context["stock_price"] == D("105.00")


def test_finance_month_snapshot(client, owner, scenario):
    client.force_login(owner)
    context = client.get(reverse("finance")).context
    month = context["month"]
    assert month["revenue"] == D("45.00")      # 3 packs × 15
    assert month["cogs"] == D("30.00")         # 3 packs × 10
    assert month["gross"] == D("15.00")
    assert month["expenses"] == D("0.00")
    assert month["net"] == D("15.00")


def test_finance_top_parties(client, owner, scenario):
    client.force_login(owner)
    context = client.get(reverse("finance")).context
    assert [p.pk for p, _b in context["top_debtors"]] == [scenario["customer"].pk]
    assert [p.pk for p, _b in context["top_creditors"]] == [scenario["supplier"].pk]
