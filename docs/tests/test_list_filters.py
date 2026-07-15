"""Party + date filters on the Transactions list (owner request: find all
documents for one customer in a period when reconciling)."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from catalog.models import Customer, Supplier
from core.models import User
from docs.models import Document, DocType

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def owner():
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


@pytest.fixture
def customer():
    return Customer.objects.create(code="C001", name="Selam Pharmacy")


@pytest.fixture
def other_customer():
    return Customer.objects.create(code="C002", name="Tana Clinic")


@pytest.fixture
def supplier():
    return Supplier.objects.create(code="S001", name="Addis Pharma")


def draft_sale(actor, customer):
    return Document.objects.create(doc_type=DocType.SALE, created_by=actor,
                                   customer=customer,
                                   sale_kind=Document.SaleKind.CREDIT)


def test_filter_by_customer(client, owner, customer, other_customer):
    mine = draft_sale(owner, customer)
    other = draft_sale(owner, other_customer)
    client.force_login(owner)
    response = client.get(reverse("document_list"), {"customer": customer.pk})
    docs = [doc.pk for doc, _state in response.context["rows"]]
    assert mine.pk in docs
    assert other.pk not in docs


def test_filter_by_supplier(client, owner, customer, supplier):
    grn = Document.objects.create(doc_type=DocType.RECEIVING, created_by=owner,
                                  supplier=supplier)
    sale = draft_sale(owner, customer)
    client.force_login(owner)
    response = client.get(reverse("document_list"), {"supplier": supplier.pk})
    docs = [doc.pk for doc, _state in response.context["rows"]]
    assert grn.pk in docs
    assert sale.pk not in docs


def test_filter_by_date_range(client, owner, customer):
    recent = draft_sale(owner, customer)
    old = draft_sale(owner, customer)
    last_month = timezone.now() - datetime.timedelta(days=40)
    Document.objects.filter(pk=old.pk).update(created_at=last_month)
    client.force_login(owner)
    today = timezone.localdate().isoformat()
    response = client.get(reverse("document_list"),
                          {"start": today, "end": today})
    docs = [doc.pk for doc, _state in response.context["rows"]]
    assert recent.pk in docs
    assert old.pk not in docs


def test_bad_date_input_ignored(client, owner, customer):
    doc = draft_sale(owner, customer)
    client.force_login(owner)
    response = client.get(reverse("document_list"),
                          {"start": "not-a-date", "end": ""})
    docs = [d.pk for d, _state in response.context["rows"]]
    assert doc.pk in docs
