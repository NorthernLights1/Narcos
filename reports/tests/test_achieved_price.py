"""D126: what each product actually sold for.

The client said items go out "at different prices to different customers" and
asked for totals per brand and per generic. The existing sales report is
line-level and keyed on item code, so it can show the rows but never the
spread. These two reports group the same posted revenue and add the price
actually achieved per base unit.
"""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Account, Customer, Item, Supplier
from core.models import CompanySettings, User
from reports.tests.test_statement import credit_sale, receive
from reports.views import REPORTS

pytestmark = pytest.mark.django_db

D = Decimal
START, END = datetime.date(2000, 1, 1), datetime.date(2030, 1, 1)


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
def supplier():
    return Supplier.objects.create(code="S001", name="Addis Pharma")


@pytest.fixture
def typed_prices(db):
    """D89: with sale prices editable, the counter types them — which is what
    makes the spread these reports exist to show."""
    settings = CompanySettings.load()
    settings.sale_price_editable = True
    settings.save()
    return settings


def _item(code, name, generic=""):
    return Item.objects.create(code=code, name=name, generic_name=generic,
                               base_unit="pack", is_batch_tracked=True,
                               has_expiry=True, maintained_price=D("15.00"))


def _rows(slug, user):
    columns, rows, total = REPORTS[slug]["builder"](START, END, user)
    return columns, rows, total


def test_the_spread_between_two_customers_is_visible(owner, supplier, customer,
                                                     typed_prices):
    item = _item("AMOX", "Amoxil")
    receive(owner, supplier, item, qty=100, cost="5.00")
    credit_sale(owner, customer, item, qty=10, price="20.00")
    credit_sale(owner, customer, item, qty=10, price="8.00")

    _cols, rows, _total = _rows("sales-by-brand", owner)
    row = next(r for r in rows if r[0].startswith("AMOX"))
    _label, qty, revenue, average, lowest, highest = row[:6]
    assert qty == 20
    assert revenue == D("280.00")          # 200.00 + 80.00
    assert average == D("14.00")           # 280 / 20
    assert (lowest, highest) == (D("8.00"), D("20.00"))


def test_grouping_by_generic_splits_spellings_but_keeps_the_total(
        owner, supplier, customer, typed_prices):
    """The reason the generic entity is worth a migration: the grand total is
    right either way, only the split moves."""
    one = _item("PARA1", "Panadol", generic="Paracetamol")
    two = _item("PARA2", "Calpol", generic="paracetamol")
    three = _item("PARA3", "Adol", generic="Paracetamoll")   # a real misspelling
    for item in (one, two, three):
        receive(owner, supplier, item, qty=50, cost="2.00")
        credit_sale(owner, customer, item, qty=10, price="10.00")

    _cols, rows, total = _rows("sales-by-generic", owner)
    labels = [r[0] for r in rows]
    # case and surrounding space fold; a misspelling does not
    assert "Paracetamol" in labels
    assert "paracetamol" not in labels
    assert "Paracetamoll" in labels
    assert total[2] == D("300.00")

    _c, brand_rows, brand_total = _rows("sales-by-brand", owner)
    assert brand_total[2] == total[2], "the grand total must not depend on grouping"


def test_items_without_a_generic_are_named_not_dropped(owner, supplier, customer,
                                                       typed_prices):
    item = _item("GLOVE", "Exam Gloves")
    receive(owner, supplier, item, qty=50, cost="1.00")
    credit_sale(owner, customer, item, qty=5, price="4.00")

    _cols, rows, total = _rows("sales-by-generic", owner)
    assert any(r[0] == "(no generic set)" for r in rows)
    assert total[2] == D("20.00")


def test_cost_and_profit_columns_are_owner_only(owner, staff, supplier, customer,
                                                typed_prices):
    item = _item("AMOX", "Amoxil")
    receive(owner, supplier, item, qty=50, cost="5.00")
    credit_sale(owner, customer, item, qty=10, price="20.00")

    owner_cols, owner_rows, _t = _rows("sales-by-brand", owner)
    staff_cols, staff_rows, _s = _rows("sales-by-brand", staff)
    assert [str(c) for c in owner_cols][-2:] == ["COGS", "Profit"]
    assert "COGS" not in [str(c) for c in staff_cols]
    assert len(staff_rows[0]) == len(staff_cols), "row width must match the header"
    assert len(owner_rows[0]) == len(owner_cols)


def test_both_reports_are_reachable_and_export(client, owner, supplier, customer,
                                               typed_prices):
    item = _item("AMOX", "Amoxil")
    receive(owner, supplier, item, qty=50, cost="5.00")
    credit_sale(owner, customer, item, qty=10, price="20.00")
    client.force_login(owner)
    for slug in ("sales-by-brand", "sales-by-generic"):
        assert client.get(reverse("report_detail", args=[slug])).status_code == 200
        csv = client.get(reverse("report_detail", args=[slug]), {"format": "csv"})
        assert csv.status_code == 200
        assert "Avg price / base unit" in csv.content.decode()
