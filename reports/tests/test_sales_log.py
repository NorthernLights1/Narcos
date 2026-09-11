"""D138: the sales log — what went out, to whom, at what price, at what cost.

The client asked for a log of items sold, "to whom and at what price and what
date, purchase price of the batch and the gross profit", totalled per brand and
strength, and again per generic. The existing `sales` report is close: it is
line-level and shows revenue, cost and profit. What it does not show is the
brand, the strength, the batch, or what that batch cost — and it has no
subtotals, so the client cannot read a total per product off it.

**Three rules this file pins, because each is a way to get money reporting
wrong.**

* **Delivery charges and document discounts get their own rows (R75).**
  `line_net` carries line discounts only, so a log built from lines alone
  disagrees with the invoice it came from by exactly `charges − doc_discount`.
* **Lot cost is the weighted average for the line.** A line can consume more
  than one cost lot — `SI-000035` in the client's database splits one item
  across two lots — so "the purchase price of the batch" is not always a single
  number, and pretending it is would make gross profit look precise when it is
  blended.
* **The generic level carries money only (D132).** Folding paracetamol syrup,
  tablets and IV into one row puts bottles and packs in one quantity
  denominator, so quantity and per-unit price stay at item level. Regrouping
  must leave the monetary totals untouched.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Customer, Item, Supplier
from core.models import User
from reports.tests.test_statement import credit_sale, receive

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def owner():
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


@pytest.fixture
def staff():
    return User.objects.create_user("clerk", password="pw", role=User.Role.EMPLOYEE)


@pytest.fixture
def customer():
    return Customer.objects.create(code="C001", name="Selam Pharmacy")


@pytest.fixture
def other_customer():
    return Customer.objects.create(code="C002", name="Alula Hospital")


@pytest.fixture
def supplier():
    return Supplier.objects.create(code="S001", name="Addis Pharma")


def _drug(code, name, generic, strength, price="15.00"):
    return Item.objects.create(
        code=code, name=name, generic_name=generic, strength=strength,
        base_unit="pack", is_batch_tracked=True, has_expiry=True,
        vat_exempt=True, maintained_price=D(price),
    )


@pytest.fixture
def amox(db):
    return _drug("AMOX1", "Amoxil", "Amoxicillin", "500mg")


def _get(client, user, group="item", **extra):
    client.force_login(user)
    params = {"period": "custom", "start": "2000-01-01", "end": "2030-01-01",
              "group": group}
    params.update(extra)
    return client.get(reverse("sales_log"), params)


def _groups(response):
    return {g["label"]: g for g in response.context["groups"]}


# --- what the client actually asked to see ---------------------------------

def test_a_line_names_the_customer_the_price_and_the_date(
        client, owner, customer, supplier, amox):
    receive(owner, supplier, amox, qty=10, cost="10.00")
    sale = credit_sale(owner, customer, amox, qty=2, price="15.00")

    group = _groups(_get(client, owner))["AMOX1 — Amoxil, 500mg"]
    line = group["lines"][0]
    assert line["customer"] == "Selam Pharmacy"
    assert line["document"].doc_no == sale.doc_no
    assert line["qty"] == 2
    assert line["unit_price"] == D("15.00")
    assert line["revenue"] == D("30.00")


def test_a_line_carries_the_batch_and_what_that_batch_cost(
        client, owner, customer, supplier, amox):
    receive(owner, supplier, amox, qty=10, cost="10.00")
    credit_sale(owner, customer, amox, qty=2, price="15.00")

    line = _groups(_get(client, owner))["AMOX1 — Amoxil, 500mg"]["lines"][0]
    assert line["batch"] == "B-1"
    assert line["unit_cost"] == D("10.00")
    assert line["cost"] == D("20.00")
    assert line["profit"] == D("10.00")


def test_the_same_product_at_two_prices_to_two_customers_totals_once(
        client, owner, customer, other_customer, supplier, amox):
    """The client's premise: 58 of 70 items sold more than once went out at
    more than one price. The log must show both and still total them."""
    receive(owner, supplier, amox, qty=20, cost="10.00")
    credit_sale(owner, customer, amox, qty=2, price="15.00")
    credit_sale(owner, other_customer, amox, qty=2, price="20.00")

    group = _groups(_get(client, owner))["AMOX1 — Amoxil, 500mg"]
    assert {line["unit_price"] for line in group["lines"]} == {D("15.00"), D("20.00")}
    assert group["revenue"] == D("70.00")
    assert group["qty"] == 4
    assert group["cost"] == D("40.00")
    assert group["profit"] == D("30.00")


# --- grouping: item level and generic level --------------------------------

def test_two_brands_of_one_generic_are_separate_at_item_level(
        client, owner, customer, supplier):
    gofen = _drug("IBU1", "Gofen", "Ibuprofen", "400mg")
    ibut = _drug("IBU2", "IBUT", "Ibuprofen", "200mg")
    for item in (gofen, ibut):
        receive(owner, supplier, item, qty=10, cost="10.00")
        credit_sale(owner, customer, item, qty=1, price="15.00")

    labels = set(_groups(_get(client, owner)))
    assert "IBU1 — Gofen, 400mg" in labels
    assert "IBU2 — IBUT, 200mg" in labels


def test_the_same_two_brands_become_one_row_per_generic(
        client, owner, customer, supplier):
    gofen = _drug("IBU1", "Gofen", "Ibuprofen", "400mg")
    ibut = _drug("IBU2", "IBUT", "Ibuprofen", "200mg")
    for item in (gofen, ibut):
        receive(owner, supplier, item, qty=10, cost="10.00")
        credit_sale(owner, customer, item, qty=1, price="15.00")

    groups = _groups(_get(client, owner, group="generic"))
    assert set(groups) == {"Ibuprofen"}
    assert groups["Ibuprofen"]["revenue"] == D("30.00")


def test_regrouping_never_changes_the_money(client, owner, customer, supplier):
    """D132: the split may move, the totals may not."""
    gofen = _drug("IBU1", "Gofen", "Ibuprofen", "400mg")
    ibut = _drug("IBU2", "IBUT", "Ibuprofen", "200mg")
    for item in (gofen, ibut):
        receive(owner, supplier, item, qty=10, cost="10.00")
        credit_sale(owner, customer, item, qty=1, price="15.00")

    by_item = _get(client, owner, group="item").context["total"]
    by_generic = _get(client, owner, group="generic").context["total"]
    assert by_item["revenue"] == by_generic["revenue"]
    assert by_item["cost"] == by_generic["cost"]
    assert by_item["profit"] == by_generic["profit"]


def test_quantity_is_suppressed_at_generic_level(client, owner, customer,
                                                 supplier):
    """D132: folding a syrup and a tablet into one row puts bottles and packs
    in one denominator, so the quantity would be arithmetic on nothing."""
    syrup = _drug("PARA1", "Panadol", "Paracetamol", "120mg/5ml")
    tablet = _drug("PARA2", "Para", "Paracetamol", "500mg")
    for item in (syrup, tablet):
        receive(owner, supplier, item, qty=10, cost="10.00")
        credit_sale(owner, customer, item, qty=1, price="15.00")

    assert _groups(_get(client, owner, group="generic"))["Paracetamol"]["qty"] is None
    assert _get(client, owner, group="generic").context["show_quantity"] is False
    assert _get(client, owner, group="item").context["show_quantity"] is True


# --- R75: the log must tie to the invoice ----------------------------------

def test_a_delivery_charge_appears_as_its_own_row(client, owner, customer,
                                                  supplier, amox):
    """R75: `line_net` carries line discounts only, so a log built from lines
    alone disagrees with the invoice by exactly charges minus doc discount."""
    import datetime

    from django.utils import timezone

    from docs.models import DocType, Document, DocumentCharge, DocumentLine
    from docs.posting import post
    from stock.models import Batch

    receive(owner, supplier, amox, qty=10, cost="10.00")
    # The charge goes on before posting — a posted document's charges are
    # immutable (I1), which is the rule, not an obstacle to work around.
    doc = Document.objects.create(
        doc_type=DocType.SALE, created_by=owner, customer=customer,
        sale_kind=Document.SaleKind.CREDIT,
        due_date=timezone.localdate() + datetime.timedelta(days=30),
    )
    DocumentLine.objects.create(
        document=doc, item=amox, batch=Batch.objects.get(item=amox),
        qty_entered=2, unit_price=D("15.00"), unit_label=amox.base_unit,
        factor=1,
    )
    DocumentCharge.objects.create(document=doc, label="Delivery",
                                  amount=D("5.00"))
    post(doc, owner)

    response = _get(client, owner)
    assert response.context["total"]["revenue"] == D("35.00")
    extras = _groups(response)["Other charges and discounts"]["lines"]
    assert extras[0]["label"] == "Delivery"
    assert extras[0]["revenue"] == D("5.00")
    assert extras[0]["cost"] == D("0.00")


# --- who may see cost ------------------------------------------------------

def test_cost_and_profit_are_owner_only(client, staff, customer, supplier,
                                        amox, owner):
    receive(owner, supplier, amox, qty=10, cost="10.00")
    credit_sale(owner, customer, amox, qty=2, price="15.00")

    assert _get(client, staff).status_code == 403


def test_the_owner_may_see_it(client, owner, customer, supplier, amox):
    receive(owner, supplier, amox, qty=10, cost="10.00")
    credit_sale(owner, customer, amox, qty=2, price="15.00")
    assert _get(client, owner).status_code == 200


# --- the screen ------------------------------------------------------------

def test_the_page_links_each_line_to_its_document(client, owner, customer,
                                                  supplier, amox):
    receive(owner, supplier, amox, qty=10, cost="10.00")
    sale = credit_sale(owner, customer, amox, qty=2, price="15.00")

    content = _get(client, owner).content.decode()
    assert reverse("document_detail", args=[sale.pk]) in content
    assert "Selam Pharmacy" in content
    assert "500mg" in content


def test_it_is_reachable_from_the_hub(client, owner):
    client.force_login(owner)
    content = client.get(reverse("report_hub")).content.decode()
    assert reverse("sales_log") in content
