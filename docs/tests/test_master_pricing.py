"""Rule: selling prices live on the item master only. Sale / proforma /
consignment-issue lines take the master price server-side no matter what the
browser submits; discounts are the sanctioned way to charge less. Items with
no usable price are refused on those lines."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from catalog.models import Customer, Item
from core.models import User
from docs.models import Document, DocType
from stock.models import CostLot

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def owner():
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


@pytest.fixture
def customer():
    return Customer.objects.create(code="C001", name="Selam Pharmacy")


@pytest.fixture
def priced_item():
    return Item.objects.create(
        code="GLOVE", name="Exam Gloves", base_unit="pair",
        is_batch_tracked=False, has_expiry=False, vat_exempt=True,
        maintained_price=D("10.00"),
    )


def _mgmt(prefix, total=1):
    return {
        f"{prefix}-TOTAL_FORMS": str(total),
        f"{prefix}-INITIAL_FORMS": "0",
        f"{prefix}-MIN_NUM_FORMS": "0",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }


def _sale_payload(customer, item, unit_price="0.40", line_discount="0"):
    due = (timezone.localdate() + datetime.timedelta(days=30)).isoformat()
    return {
        "customer": str(customer.pk),
        "sale_kind": Document.SaleKind.CREDIT,
        "due_date": due,
        "doc_discount": "0",
        "fiscal_receipt_no": "",
        "machine_total": "",
        "notes": "",
        "lines-0-item": str(item.pk),
        "lines-0-batch": "",
        "lines-0-unit_label": "pair",
        "lines-0-factor": "1",
        "lines-0-qty_entered": "5",
        "lines-0-unit_price": unit_price,
        "lines-0-line_discount": line_discount,
    } | _mgmt("lines") | _mgmt("charges", 0) | _mgmt("payments", 0)


def test_sale_line_price_comes_from_master(client, owner, customer, priced_item):
    client.force_login(owner)
    response = client.post(
        reverse("document_create", args=[DocType.SALE]),
        _sale_payload(customer, priced_item, unit_price="0.40"),
    )
    assert response.status_code == 302
    line = Document.objects.get(doc_type=DocType.SALE).lines.get()
    assert line.unit_price == D("10.00")


def test_line_discount_still_honoured(client, owner, customer, priced_item):
    client.force_login(owner)
    response = client.post(
        reverse("document_create", args=[DocType.SALE]),
        _sale_payload(customer, priced_item, unit_price="10.00",
                      line_discount="2.00"),
    )
    assert response.status_code == 302
    line = Document.objects.get(doc_type=DocType.SALE).lines.get()
    assert line.unit_price == D("10.00")
    assert line.line_discount == D("2.00")


def test_sale_refused_when_item_has_no_price(client, owner, customer):
    unpriced = Item.objects.create(
        code="NP", name="No price yet", base_unit="unit",
        is_batch_tracked=False, has_expiry=False, maintained_price=D("0"),
    )
    client.force_login(owner)
    response = client.post(
        reverse("document_create", args=[DocType.SALE]),
        _sale_payload(customer, unpriced, unit_price="5.00"),
    )
    assert response.status_code == 200  # re-rendered with errors
    assert not Document.objects.filter(doc_type=DocType.SALE).exists()


def test_auto_item_priced_from_cost_plus_margin(client, owner, customer):
    auto_item = Item.objects.create(
        code="AUTO", name="Auto priced", base_unit="unit",
        is_batch_tracked=False, has_expiry=False,
        pricing_mode=Item.PricingMode.AUTO, auto_margin_pct=D("50"),
        maintained_price=D("0"),
    )
    CostLot.objects.create(item=auto_item, received_at=timezone.now(),
                           qty_received=10, unit_cost=D("10.00"))
    client.force_login(owner)
    response = client.post(
        reverse("document_create", args=[DocType.SALE]),
        _sale_payload(customer, auto_item, unit_price="1.00"),
    )
    assert response.status_code == 302
    line = Document.objects.get(doc_type=DocType.SALE).lines.get()
    assert line.unit_price == D("15.00")


def test_auto_item_without_stock_refused(client, owner, customer):
    auto_item = Item.objects.create(
        code="AUTO2", name="Auto no stock", base_unit="unit",
        is_batch_tracked=False, has_expiry=False,
        pricing_mode=Item.PricingMode.AUTO, auto_margin_pct=D("50"),
        maintained_price=D("0"),
    )
    client.force_login(owner)
    response = client.post(
        reverse("document_create", args=[DocType.SALE]),
        _sale_payload(customer, auto_item, unit_price="1.00"),
    )
    assert response.status_code == 200
    assert not Document.objects.filter(doc_type=DocType.SALE).exists()


def test_consignment_issue_price_locked_to_master(client, owner, customer,
                                                  priced_item):
    client.force_login(owner)
    due = (timezone.localdate() + datetime.timedelta(days=30)).isoformat()
    response = client.post(
        reverse("document_create", args=[DocType.CONSIGNMENT_ISSUE]),
        {
            "customer": str(customer.pk),
            "due_date": due,
            "doc_discount": "0",
            "notes": "",
            "lines-0-item": str(priced_item.pk),
            "lines-0-batch": "",
            "lines-0-unit_label": "pair",
            "lines-0-factor": "1",
            "lines-0-qty_entered": "5",
            "lines-0-unit_price": "0.40",
            "lines-0-line_discount": "0",
        } | _mgmt("lines"),
    )
    assert response.status_code == 302
    line = Document.objects.get(doc_type=DocType.CONSIGNMENT_ISSUE).lines.get()
    assert line.unit_price == D("10.00")
