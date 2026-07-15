"""Party statement — the reconciliation view: opening balance, every AR/AP
movement in the period with a running balance, closing balance. Built on
PartyLedger, so it inherits the engine's exactness (posted docs only, voids
appear as reversals)."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from catalog.models import Account, Customer, Item, Supplier
from core.models import User
from docs.models import Document, DocType, DocumentLine
from docs.posting import post, void
from money.models import PaymentAllocation, PaymentLine
from stock.models import Batch

pytestmark = pytest.mark.django_db

D = Decimal
FAR_EXPIRY = datetime.date(2030, 1, 1)


@pytest.fixture
def owner():
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


@pytest.fixture
def cash():
    return Account.objects.create(name="Cash drawer", type=Account.Type.CASH)


@pytest.fixture
def customer():
    return Customer.objects.create(code="C001", name="Selam Pharmacy")


@pytest.fixture
def supplier():
    return Supplier.objects.create(code="S001", name="Addis Pharma")


@pytest.fixture
def drug():
    return Item.objects.create(
        code="AMOX", name="Amoxicillin", base_unit="pack",
        is_batch_tracked=True, has_expiry=True, vat_exempt=True,
        maintained_price=D("15.00"),
    )


def receive(actor, supplier, item, qty=10, cost="10.00"):
    doc = Document.objects.create(doc_type=DocType.RECEIVING, created_by=actor,
                                  supplier=supplier)
    DocumentLine.objects.create(
        document=doc, item=item, qty_entered=qty, unit_cost_entered=D(cost),
        batch_no_entered="B-1", expiry_entered=FAR_EXPIRY,
        unit_label=item.base_unit, factor=1,
    )
    return post(doc, actor)


def credit_sale(actor, customer, item, qty=2, price="15.00"):
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=actor,
                                  customer=customer,
                                  sale_kind=Document.SaleKind.CREDIT,
                                  due_date=timezone.localdate()
                                  + datetime.timedelta(days=30))
    DocumentLine.objects.create(
        document=doc, item=item, batch=Batch.objects.get(item=item),
        qty_entered=qty, unit_price=D(price), unit_label=item.base_unit, factor=1,
    )
    return post(doc, actor)


def customer_payment(actor, customer, target, account, amount):
    doc = Document.objects.create(doc_type=DocType.CUSTOMER_PAYMENT,
                                  created_by=actor, customer=customer)
    PaymentLine.objects.create(document=doc, account=account, amount=D(amount))
    PaymentAllocation.objects.create(payment=doc, target=target, amount=D(amount))
    return post(doc, actor)


def cash_sale(actor, customer, item, account, qty=1, price="15.00"):
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=actor,
                                  customer=customer,
                                  sale_kind=Document.SaleKind.CASH)
    DocumentLine.objects.create(
        document=doc, item=item, batch=Batch.objects.get(item=item),
        qty_entered=qty, unit_price=D(price), unit_label=item.base_unit, factor=1,
    )
    PaymentLine.objects.create(document=doc, account=account,
                               amount=D(price) * qty)
    return post(doc, actor)


def _params(**extra):
    today = timezone.localdate().isoformat()
    params = {"period": "custom", "start": today, "end": today}
    params.update(extra)
    return params


def test_statement_requires_login(client):
    response = client.get(reverse("statement"))
    assert response.status_code == 302


def test_picker_renders_without_party(client, owner):
    client.force_login(owner)
    response = client.get(reverse("statement"))
    assert response.status_code == 200
    assert b"closing" not in response.content.lower()


def test_customer_statement_running_balance(client, owner, cash, customer,
                                            supplier, drug):
    receive(owner, supplier, drug)
    sale = credit_sale(owner, customer, drug, qty=2, price="15.00")   # +30
    customer_payment(owner, customer, sale, cash, "10.00")            # -10
    client.force_login(owner)
    response = client.get(
        reverse("statement"),
        _params(party_type="customer", party=customer.pk),
    )
    content = response.content.decode()
    assert sale.doc_no in content
    assert response.context["opening"] == D("0.00")
    assert response.context["closing"] == D("20.00")
    balances = [entry["balance"] for entry in response.context["entries"]]
    assert balances == [D("30.00"), D("20.00")]


def test_supplier_statement_shows_payable(client, owner, supplier, drug):
    grn = receive(owner, supplier, drug, qty=10, cost="10.00")        # we owe 100
    client.force_login(owner)
    response = client.get(
        reverse("statement"),
        _params(party_type="supplier", party=supplier.pk),
    )
    assert grn.doc_no in response.content.decode()
    assert response.context["closing"] == D("100.00")


def test_statement_excludes_other_parties(client, owner, cash, supplier, drug):
    receive(owner, supplier, drug)
    first = Customer.objects.create(code="C001", name="Selam Pharmacy")
    second = Customer.objects.create(code="C002", name="Tana Clinic")
    sale_first = credit_sale(owner, first, drug, qty=1)
    sale_second = credit_sale(owner, second, drug, qty=1)
    client.force_login(owner)
    response = client.get(
        reverse("statement"), _params(party_type="customer", party=first.pk),
    )
    content = response.content.decode()
    assert sale_first.doc_no in content
    assert sale_second.doc_no not in content


def test_cash_sale_absent_from_statement(client, owner, cash, customer,
                                         supplier, drug):
    receive(owner, supplier, drug)
    cash_doc = cash_sale(owner, customer, drug, cash)
    client.force_login(owner)
    response = client.get(
        reverse("statement"), _params(party_type="customer", party=customer.pk),
    )
    assert cash_doc.doc_no not in response.content.decode()
    assert response.context["closing"] == D("0.00")


def test_void_appears_as_reversal_netting_zero(client, owner, cash, customer,
                                               supplier, drug):
    receive(owner, supplier, drug)
    sale = credit_sale(owner, customer, drug, qty=2, price="15.00")
    void(sale, owner, reason="demo mistake")
    client.force_login(owner)
    response = client.get(
        reverse("statement"), _params(party_type="customer", party=customer.pk),
    )
    assert response.context["closing"] == D("0.00")
    entries = response.context["entries"]
    assert len(entries) == 2
    assert entries[1]["is_reversal"] is True


def test_opening_balance_carries_prior_activity(client, owner, cash, customer,
                                                supplier, drug):
    receive(owner, supplier, drug)
    credit_sale(owner, customer, drug, qty=2, price="15.00")          # +30 today
    tomorrow = (timezone.localdate() + datetime.timedelta(days=1)).isoformat()
    client.force_login(owner)
    response = client.get(
        reverse("statement"),
        _params(party_type="customer", party=customer.pk,
                start=tomorrow, end=tomorrow),
    )
    assert response.context["opening"] == D("30.00")
    assert response.context["entries"] == []
    assert response.context["closing"] == D("30.00")


def test_tin_crossref_shows_counterpart_position(client, owner, cash, supplier,
                                                 drug):
    """A fellow vendor is both customer and supplier (same TIN): each
    statement points at the other side's balance."""
    receive(owner, supplier, drug, qty=10, cost="10.00")   # we owe 100
    supplier.tin = "0099887766"
    supplier.save()
    twin = Customer.objects.create(code="C009", name="Addis Pharma",
                                   tin="0099887766")
    credit_sale(owner, twin, drug, qty=2, price="15.00")   # they owe 30
    client.force_login(owner)
    response = client.get(
        reverse("statement"), _params(party_type="customer", party=twin.pk),
    )
    counterpart = response.context["counterpart"]
    assert counterpart["party"].pk == supplier.pk
    assert counterpart["balance"] == D("100.00")
    response = client.get(
        reverse("statement"), _params(party_type="supplier", party=supplier.pk),
    )
    counterpart = response.context["counterpart"]
    assert counterpart["party"].pk == twin.pk
    assert counterpart["balance"] == D("30.00")


def test_statement_csv_export(client, owner, cash, customer, supplier, drug):
    receive(owner, supplier, drug)
    credit_sale(owner, customer, drug)
    client.force_login(owner)
    response = client.get(
        reverse("statement"),
        _params(party_type="customer", party=customer.pk, format="csv"),
    )
    assert response["Content-Type"] == "text/csv"
    body = response.content.decode()
    assert "Opening balance" in body
    assert "Closing balance" in body
