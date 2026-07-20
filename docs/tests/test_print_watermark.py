"""Print hygiene: sale/consignment printouts carry an ATTACHMENT watermark
(the legal invoice is the government-vendor fiscal pad, D18 — our page must
never pass for it), and internal master codes stay off paper the other
business files."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

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
def customer():
    return Customer.objects.create(code="C001", name="Selam Pharmacy")


@pytest.fixture
def supplier():
    return Supplier.objects.create(code="S001", name="Addis Pharma")


@pytest.fixture
def stocked_item(owner, supplier):
    item = Item.objects.create(
        code="AMOX", name="Amoxicillin", base_unit="pack",
        is_batch_tracked=True, has_expiry=True, vat_exempt=True,
        maintained_price=D("15.00"),
    )
    grn = Document.objects.create(doc_type=DocType.RECEIVING,
                                  created_by=owner, supplier=supplier)
    DocumentLine.objects.create(
        document=grn, item=item, qty_entered=10, unit_cost_entered=D("10.00"),
        batch_no_entered="B-1", expiry_entered=FAR_EXPIRY,
        unit_label=item.base_unit, factor=1,
    )
    post(grn, owner)
    return item


def _posted_cash_sale(owner, customer, item):
    cash = Account.objects.create(name="Cash drawer", type=Account.Type.CASH)
    sale = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                   customer=customer,
                                   sale_kind=Document.SaleKind.CASH)
    DocumentLine.objects.create(
        document=sale, item=item, batch=Batch.objects.get(item=item),
        qty_entered=2, unit_price=D("15.00"),
        unit_label=item.base_unit, factor=1,
    )
    PaymentLine.objects.create(document=sale, account=cash, amount=D("30.00"))
    return post(sale, owner)


def test_sale_print_has_attachment_watermark(client, owner, customer,
                                             stocked_item):
    sale = _posted_cash_sale(owner, customer, stocked_item)
    client.force_login(owner)
    html = client.get(reverse("document_print", args=[sale.pk])).content.decode()
    assert 'class="watermark"' in html
    assert "ATTACHMENT" in html


def test_consignment_issue_print_has_watermark(client, owner, customer,
                                               stocked_item):
    issue = Document.objects.create(doc_type=DocType.CONSIGNMENT_ISSUE,
                                    created_by=owner, customer=customer)
    DocumentLine.objects.create(
        document=issue, item=stocked_item,
        batch=Batch.objects.get(item=stocked_item),
        qty_entered=3, unit_price=D("15.00"),
        unit_label=stocked_item.base_unit, factor=1,
    )
    post(issue, owner)
    client.force_login(owner)
    html = client.get(reverse("document_print", args=[issue.pk])).content.decode()
    assert 'class="watermark"' in html


def test_internal_document_print_has_no_watermark(client, owner, supplier,
                                                  stocked_item):
    grn = Document.objects.get(doc_type=DocType.RECEIVING)
    client.force_login(owner)
    html = client.get(reverse("document_print", args=[grn.pk])).content.decode()
    assert 'class="watermark"' not in html


def test_print_shows_party_name_without_master_code(client, owner, customer,
                                                    stocked_item):
    sale = _posted_cash_sale(owner, customer, stocked_item)
    client.force_login(owner)
    html = client.get(reverse("document_print", args=[sale.pk])).content.decode()
    assert "Selam Pharmacy" in html
    assert "C001" not in html


def test_sales_attachment_layout_has_watermark(client, owner, customer,
                                               stocked_item):
    sale = _posted_cash_sale(owner, customer, stocked_item)
    client.force_login(owner)
    html = client.get(reverse("document_print", args=[sale.pk]),
                      {"layout": "SALES_ATT"}).content.decode()
    assert 'class="watermark"' in html


def test_print_leaks_no_template_comment(client, owner, customer,
                                         stocked_item):
    # Django {# #} comments must stay on one line; a wrapped one renders
    # as literal text on the printout.
    sale = _posted_cash_sale(owner, customer, stocked_item)
    client.force_login(owner)
    html = client.get(reverse("document_print", args=[sale.pk])).content.decode()
    assert "{#" not in html
    assert "master codes" not in html


def test_print_shows_customer_tin(client, owner, customer, stocked_item):
    customer.tin = "0012345678"
    customer.save()
    sale = _posted_cash_sale(owner, customer, stocked_item)
    client.force_login(owner)
    html = client.get(reverse("document_print", args=[sale.pk])).content.decode()
    assert "0012345678" in html


def test_print_shows_supplier_tin(client, owner, supplier, stocked_item):
    supplier.tin = "0087654321"
    supplier.save()
    grn = Document.objects.get(doc_type=DocType.RECEIVING)
    client.force_login(owner)
    html = client.get(reverse("document_print", args=[grn.pk])).content.decode()
    assert "0087654321" in html
