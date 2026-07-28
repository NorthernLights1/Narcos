"""D90 — "Correct this document": void the wrong paper and hand back an
editable copy in one click.

The books still work the way they always have (you never erase, you
reverse); this only removes the retyping that made fixing a mistake
expensive."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Account, Customer, Item, Supplier
from core.models import User
from docs.models import Document, DocType, DocumentCharge, DocumentLine
from docs.posting import post
from money.models import PaymentLine
from stock.models import Batch

pytestmark = pytest.mark.django_db

D = Decimal
FAR_EXPIRY = datetime.date(2030, 1, 1)


@pytest.fixture
def customer():
    return Customer.objects.create(code="C001", name="Selam Pharmacy")


@pytest.fixture
def supplier():
    return Supplier.objects.create(code="S001", name="Addis Pharma")


@pytest.fixture
def stocked_item(owner, supplier):
    item = Item.objects.create(code="AMOX", name="Amoxicillin",
                               base_unit="pack", is_batch_tracked=True,
                               has_expiry=True, vat_exempt=True,
                               maintained_price=D("15.00"))
    grn = Document.objects.create(doc_type=DocType.RECEIVING,
                                  created_by=owner, supplier=supplier)
    DocumentLine.objects.create(
        document=grn, item=item, qty_entered=10, unit_cost_entered=D("10.00"),
        batch_no_entered="B-1", expiry_entered=FAR_EXPIRY,
        unit_label=item.base_unit, factor=1,
    )
    post(grn, owner)
    return item


def _posted_sale(owner, customer, item, qty=2):
    cash = Account.objects.create(name="Cash drawer", type=Account.Type.CASH)
    sale = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                   customer=customer,
                                   sale_kind=Document.SaleKind.CASH,
                                   notes="original")
    DocumentLine.objects.create(
        document=sale, item=item, batch=Batch.objects.get(item=item),
        qty_entered=qty, unit_price=D("15.00"),
        unit_label=item.base_unit, factor=1,
    )
    DocumentCharge.objects.create(document=sale, label="Delivery",
                                  amount=D("3.00"), is_taxable=False)
    PaymentLine.objects.create(document=sale, account=cash,
                               amount=D("15.00") * qty + D("3.00"))
    return post(sale, owner)


def test_correcting_voids_the_original_and_opens_a_draft_copy(
        client, owner, customer, stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(owner)

    response = client.post(reverse("document_correct", args=[sale.pk]),
                           {"reason": "wrong quantity"})

    sale.refresh_from_db()
    assert sale.status == Document.Status.VOIDED
    assert sale.void_reason == "wrong quantity"

    draft = Document.objects.get(doc_type=DocType.SALE,
                                 status=Document.Status.DRAFT)
    assert response.status_code == 302
    assert response.url == reverse("document_edit", args=[draft.pk])
    # A draft has no number of its own until it is posted (D8)
    assert not draft.doc_no


def test_the_copy_carries_the_whole_document(client, owner, customer,
                                             stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(owner)
    client.post(reverse("document_correct", args=[sale.pk]),
                {"reason": "wrong price"})

    draft = Document.objects.get(status=Document.Status.DRAFT,
                                 doc_type=DocType.SALE)
    assert draft.customer == customer
    assert draft.sale_kind == sale.sale_kind

    line = draft.lines.get()
    assert line.item == stocked_item
    assert line.qty_entered == 2
    assert line.unit_price == D("15.00")
    assert draft.charges.get().label == "Delivery"
    assert draft.payment_lines.get().amount == D("33.00")


def test_the_copy_points_back_at_what_it_replaces(client, owner, customer,
                                                  stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(owner)
    client.post(reverse("document_correct", args=[sale.pk]),
                {"reason": "wrong quantity"})
    draft = Document.objects.get(status=Document.Status.DRAFT,
                                 doc_type=DocType.SALE)
    assert sale.doc_no in draft.notes


def test_a_reason_is_required(client, owner, customer, stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(owner)
    client.post(reverse("document_correct", args=[sale.pk]), {"reason": ""})

    sale.refresh_from_db()
    assert sale.status == Document.Status.POSTED
    assert not Document.objects.filter(status=Document.Status.DRAFT).exists()


def test_only_the_owner_may_correct(client, employee, owner, customer,
                                    stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(employee)
    response = client.post(reverse("document_correct", args=[sale.pk]),
                           {"reason": "wrong quantity"})
    assert response.status_code == 403
    sale.refresh_from_db()
    assert sale.status == Document.Status.POSTED


def test_nothing_happens_when_the_void_is_refused(client, owner, customer,
                                                  supplier, stocked_item):
    """D5: a receiving whose goods were already sold cannot be voided —
    so it cannot be 'corrected' either, and no orphan draft is left."""
    _posted_sale(owner, customer, stocked_item)          # consumes the lot
    grn = Document.objects.get(doc_type=DocType.RECEIVING)
    client.force_login(owner)

    response = client.post(reverse("document_correct", args=[grn.pk]),
                           {"reason": "wrong cost"})

    grn.refresh_from_db()
    assert grn.status == Document.Status.POSTED
    assert response.status_code == 302
    assert not Document.objects.filter(doc_type=DocType.RECEIVING,
                                       status=Document.Status.DRAFT).exists()


def test_a_draft_cannot_be_corrected(client, owner, customer, stocked_item):
    draft = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                    customer=customer)
    client.force_login(owner)
    response = client.post(reverse("document_correct", args=[draft.pk]),
                           {"reason": "typo"})
    assert response.status_code == 404


def test_posted_page_offers_the_button(client, owner, customer, stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(owner)
    html = client.get(reverse("document_detail", args=[sale.pk])).content.decode()
    assert reverse("document_correct", args=[sale.pk]) in html


def test_employees_are_not_offered_the_button(client, employee, owner,
                                              customer, stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(employee)
    html = client.get(reverse("document_detail", args=[sale.pk])).content.decode()
    assert reverse("document_correct", args=[sale.pk]) not in html
