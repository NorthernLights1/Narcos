"""D135: who owes money and who we have not paid, drilling from a party total
down to the transactions behind it.

Three reports already answered pieces of this and none of them joined up:
`ar-balances` gives a party total, `ar-aging` gives open documents, and
`both-faces` nets a business that is on both sides. The client asked for one
screen that starts at the party, expands to the transactions, and links to the
document.

**The invariant this file exists to defend.** The party total is the PartyLedger
balance, and the drill-down is a list of open documents. Those two are not the
same sum, and assuming they are is how a screen ends up disagreeing with itself.
An owner may post a customer return with no sale reference
(docs/handlers_sales.py); with no refund lines it credits the party ledger
directly and hangs off no invoice, so it is in the balance and in no open
document. The report must show that difference on its own row rather than
silently swallow it or silently disagree.
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from catalog.models import Account, Customer, Item, Supplier
from core.models import User
from docs.models import DocType, Document, DocumentLine
from docs.posting import post
from stock.models import Batch, Zone
from reports.tests.test_statement import (
    credit_sale,
    customer_payment,
    receive,
)

pytestmark = pytest.mark.django_db

D = Decimal


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


def _get(client, owner, side="receivable", **extra):
    client.force_login(owner)
    today = timezone.localdate().isoformat()
    params = {"period": "custom", "start": today, "end": today}
    params.update(extra)
    return client.get(reverse("party_positions", args=[side]), params)


def _row(response, code):
    return next(r for r in response.context["rows"] if r["party"].code == code)


# --- level one: the party total is the ledger balance ----------------------

def test_the_party_total_is_the_ledger_balance(client, owner, customer,
                                               supplier, drug):
    receive(owner, supplier, drug, qty=10)
    credit_sale(owner, customer, drug, qty=2, price="15.00")

    row = _row(_get(client, owner), "C001")
    assert row["balance"] == D("30.00")


def test_the_drill_down_lists_the_open_documents_behind_it(client, owner,
                                                           customer, supplier,
                                                           drug):
    receive(owner, supplier, drug, qty=10)
    sale = credit_sale(owner, customer, drug, qty=2, price="15.00")

    row = _row(_get(client, owner), "C001")
    assert [d["document"].doc_no for d in row["documents"]] == [sale.doc_no]
    entry = row["documents"][0]
    assert entry["original"] == D("30.00")
    assert entry["settled"] == D("0.00")
    assert entry["open"] == D("30.00")


def test_a_partial_payment_reduces_the_open_amount_not_the_original(
        client, owner, customer, supplier, drug, cash):
    receive(owner, supplier, drug, qty=10)
    sale = credit_sale(owner, customer, drug, qty=2, price="15.00")
    customer_payment(owner, customer, sale, cash, "10.00")

    row = _row(_get(client, owner), "C001")
    entry = row["documents"][0]
    assert entry["original"] == D("30.00")
    assert entry["settled"] == D("10.00")
    assert entry["open"] == D("20.00")
    assert row["balance"] == D("20.00")


def test_a_fully_settled_invoice_leaves_the_report(client, owner, customer,
                                                   supplier, drug, cash):
    receive(owner, supplier, drug, qty=10)
    sale = credit_sale(owner, customer, drug, qty=2, price="15.00")
    customer_payment(owner, customer, sale, cash, "30.00")

    assert not any(r["party"].code == "C001"
                   for r in _get(client, owner).context["rows"])


# --- the invariant: the two levels may not disagree silently ---------------

def _owner_return_without_a_reference(actor, customer, item, amount):
    """docs/handlers_sales.py: an owner may return goods with no sale to point
    at, entering the credit directly. With no refund lines it credits the party
    ledger and belongs to no invoice."""
    doc = Document.objects.create(doc_type=DocType.CUSTOMER_RETURN,
                                  created_by=actor, customer=customer)
    DocumentLine.objects.create(
        document=doc, item=item, batch=Batch.objects.get(item=item),
        qty_entered=1, unit_price=D(amount),
        unit_cost_entered=D("1.00"), unit_label=item.base_unit, factor=1,
        target_zone=Zone.WAREHOUSE,
    )
    return post(doc, actor)


def test_a_ledger_movement_with_no_open_document_gets_its_own_row(
        client, owner, customer, supplier, drug):
    """Astra found this and it is the reason level one is the ledger balance
    rather than a sum of open documents. Without the reconciling row the party
    total reads 20.00 while the transactions beneath it add to 30.00, and
    nothing on the screen explains the missing 10.00."""
    receive(owner, supplier, drug, qty=10)
    credit_sale(owner, customer, drug, qty=2, price="15.00")
    _owner_return_without_a_reference(owner, customer, drug, "10.00")

    row = _row(_get(client, owner), "C001")
    assert row["balance"] == D("20.00")
    assert row["documents_total"] == D("30.00")
    assert row["unexplained"] == D("-10.00")


def test_nothing_unexplained_when_every_movement_has_a_document(
        client, owner, customer, supplier, drug):
    receive(owner, supplier, drug, qty=10)
    credit_sale(owner, customer, drug, qty=2, price="15.00")

    row = _row(_get(client, owner), "C001")
    assert row["unexplained"] == D("0.00")
    assert row["documents_total"] == row["balance"]


# --- the payable side ------------------------------------------------------

def test_the_payable_side_lists_suppliers_we_owe(client, owner, supplier, drug):
    grn = receive(owner, supplier, drug, qty=10, cost="10.00")

    row = _row(_get(client, owner, side="payable"), "S001")
    assert row["balance"] == D("100.00")
    assert [d["document"].doc_no for d in row["documents"]] == [grn.doc_no]


def test_an_unknown_side_is_not_a_server_error(client, owner):
    assert _get(client, owner, side="sideways").status_code == 404


# --- both faces: netted on tax number, flagged when it cannot pair ---------

def test_a_business_on_both_sides_is_netted_when_the_tax_numbers_match(
        client, owner, drug):
    """Typed by people, so `001-2345678` and ` 0012345678 ` are one number."""
    buyer = Customer.objects.create(code="C010", name="Bethel w/s",
                                    tin="001-2345678")
    seller = Supplier.objects.create(code="S010", name="Bethel w/s",
                                     tin=" 0012345678 ")
    receive(owner, seller, drug, qty=10, cost="10.00")
    credit_sale(owner, buyer, drug, qty=2, price="15.00")

    row = _row(_get(client, owner), "C010")
    assert row["counterpart"] == seller
    assert row["counterpart_balance"] == D("100.00")
    assert row["net"] == D("-70.00")


def test_a_both_sided_business_with_no_tax_number_is_named_not_netted(
        client, owner, drug):
    """The client is filling tax numbers in; until they finish, a report that
    silently shows nothing reads as "nobody is on both sides". 13 of their
    businesses are on both sides and none pair by tax number today, so this
    list is the whole feature until the data catches up."""
    Customer.objects.create(code="C011", name="Girmay Wholesale")
    seller = Supplier.objects.create(code="S011", name="Girmay Wholesale")
    buyer = Customer.objects.get(code="C011")
    receive(owner, seller, drug, qty=10, cost="10.00")
    credit_sale(owner, buyer, drug, qty=2, price="15.00")

    response = _get(client, owner)
    row = _row(response, "C011")
    assert row["counterpart"] is None
    assert row["net"] is None
    assert "Girmay Wholesale" in {p["name"] for p in response.context["unpaired"]}


def test_a_name_that_exists_on_one_side_only_is_not_flagged(
        client, owner, customer, supplier, drug):
    receive(owner, supplier, drug, qty=10)
    credit_sale(owner, customer, drug, qty=2, price="15.00")

    assert _get(client, owner).context["unpaired"] == []


# --- the screen itself -----------------------------------------------------

def test_the_page_links_each_transaction_to_its_document(client, owner,
                                                         customer, supplier,
                                                         drug):
    receive(owner, supplier, drug, qty=10)
    sale = credit_sale(owner, customer, drug, qty=2, price="15.00")

    content = _get(client, owner).content.decode()
    assert reverse("document_detail", args=[sale.pk]) in content
    assert sale.doc_no in content


def test_the_report_is_reachable_from_the_hub(client, owner):
    client.force_login(owner)
    content = client.get(reverse("report_hub")).content.decode()
    assert reverse("party_positions", args=["receivable"]) in content
    assert reverse("party_positions", args=["payable"]) in content
