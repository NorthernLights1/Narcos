"""D127: who owes who, when one business is both customer and supplier.

The statement page already paired one party with its other face. This asks the
same question across everyone at once, and repairs the pairing itself — the
old lookup stripped only one side's tax number, compared it exactly, and
required the counterpart to be active.
"""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Account, Customer, Item, Supplier
from core.models import User
from reports.tests.test_statement import credit_sale, receive
from reports.views import REPORTS, _normalised_tin

pytestmark = pytest.mark.django_db

D = Decimal
START, END = datetime.date(2000, 1, 1), datetime.date(2030, 1, 1)
TIN = "0012345678"


@pytest.fixture
def owner():
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


def _item():
    # VAT-exempt, as medicines are by law here (D50) — it also keeps the
    # arithmetic below readable, since a receivable carries the invoiced
    # total including any tax, not the line net.
    return Item.objects.create(code="AMOX", name="Amoxil", base_unit="pack",
                               is_batch_tracked=True, has_expiry=True,
                               vat_exempt=True, maintained_price=D("15.00"))


def _rows(user):
    return REPORTS["both-faces"]["builder"](START, END, user)


@pytest.mark.parametrize("stored, matches", [
    ("  0012345678  ", True),    # whitespace: used to link one way only
    ("001-2345678", True),       # punctuation: used to link neither way
    ("001 2345678", True),
    ("0012345679", False),       # a genuinely different number
    ("", False),                 # blank must never pair
])
def test_tax_numbers_are_compared_on_both_sides(stored, matches):
    assert (_normalised_tin(TIN) == _normalised_tin(stored)
            and bool(_normalised_tin(stored))) is matches


def test_a_business_with_both_faces_shows_one_row_with_the_net(owner):
    customer = Customer.objects.create(code="C001", name="Selam", tin=TIN)
    supplier = Supplier.objects.create(code="S001", name="Selam Trading",
                                       tin=f" {TIN} ")   # stored with spaces
    item = _item()
    receive(owner, supplier, item, qty=100, cost="6.00")     # we owe 600
    credit_sale(owner, customer, item, qty=10, price="15.00")  # they owe 150

    _cols, rows, total = _rows(owner)
    assert len(rows) == 1
    name, cust_codes, supp_codes, ar, ap, net = rows[0]
    assert (cust_codes, supp_codes) == ("C001", "S001")
    assert ar == D("150.00")
    assert ap == D("600.00")
    assert net == D("-450.00"), "negative means the balance is in their favour"
    assert total[5] == D("-450.00")


def test_a_business_with_only_one_face_is_left_to_the_ordinary_reports(owner):
    customer = Customer.objects.create(code="C001", name="Selam", tin=TIN)
    item = _item()
    supplier = Supplier.objects.create(code="S001", name="Addis", tin="9999")
    receive(owner, supplier, item, qty=100, cost="6.00")
    credit_sale(owner, customer, item, qty=10, price="15.00")

    _cols, rows, _total = _rows(owner)
    assert rows == []


def test_an_ambiguous_tax_number_names_every_record_instead_of_guessing(owner):
    """Two suppliers share the tax number. The old statement lookup silently
    took whichever sorted first; this names both so a human can see it."""
    customer = Customer.objects.create(code="C001", name="Selam", tin=TIN)
    one = Supplier.objects.create(code="S001", name="Selam Trading", tin=TIN)
    two = Supplier.objects.create(code="S002", name="Selam Trading PLC", tin=TIN)
    item = _item()
    receive(owner, one, item, qty=100, cost="6.00")
    receive(owner, two, item, qty=50, cost="4.00")
    credit_sale(owner, customer, item, qty=10, price="15.00")

    _cols, rows, _total = _rows(owner)
    assert len(rows) == 1
    assert rows[0][2] == "S001, S002"
    assert rows[0][4] == D("800.00"), "both suppliers' payables are counted"


def test_a_deactivated_counterpart_still_shows_what_is_owed(owner):
    """Deactivating a record does not settle a debt. The statement's old
    lookup required is_active and hid it."""
    customer = Customer.objects.create(code="C001", name="Selam", tin=TIN)
    supplier = Supplier.objects.create(code="S001", name="Selam Trading", tin=TIN)
    item = _item()
    receive(owner, supplier, item, qty=100, cost="6.00")
    credit_sale(owner, customer, item, qty=10, price="15.00")
    Supplier.objects.filter(pk=supplier.pk).update(is_active=False)

    _cols, rows, _total = _rows(owner)
    assert len(rows) == 1
    assert rows[0][4] == D("600.00")


def test_the_report_is_reachable_and_exports(client, owner):
    customer = Customer.objects.create(code="C001", name="Selam", tin=TIN)
    supplier = Supplier.objects.create(code="S001", name="Selam Trading", tin=TIN)
    item = _item()
    receive(owner, supplier, item, qty=100, cost="6.00")
    credit_sale(owner, customer, item, qty=10, price="15.00")
    client.force_login(owner)
    assert client.get(reverse("report_detail", args=["both-faces"])).status_code == 200
    csv = client.get(reverse("report_detail", args=["both-faces"]), {"format": "csv"})
    assert csv.status_code == 200
    assert "Selam" in csv.content.decode()
