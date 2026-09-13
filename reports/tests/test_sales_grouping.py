"""D144: grouping the sales report per generic.

The owner asked for it on this report rather than as a fourth sales report.
Two things it must get right, both settled earlier and both easy to lose:

D132 — **money only at generic level.** One generic covers several strengths,
and 100 tablets of 500 mg plus 100 of 250 mg is not 200 of anything. Revenue
and cost add up across a generic; quantity does not.

D126 — the two reports must **split the same way**, so `sales-by-generic` and
this grouping never disagree about which rows are one generic.
"""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Customer, Item, Supplier
from core.models import CompanySettings, User
from docs.models import DocType, Document, DocumentCharge, DocumentLine
from docs.posting import post
from reports.tests.test_statement import credit_sale, receive
from reports.views import _generic_groups, _sale_line_rows
from stock.models import Batch

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
def client_settings(db):
    settings = CompanySettings.load()
    settings.sale_price_editable = True
    settings.tax_regime = CompanySettings.TaxRegime.NONE
    settings.save()
    return settings


def _item(code, brand, generic="", strength=""):
    return Item.objects.create(code=code, name=brand, generic_name=generic,
                               strength=strength, base_unit="pack",
                               is_batch_tracked=True, has_expiry=True,
                               maintained_price=D("15.00"))


def _groups(**filters):
    rows, totals = _sale_line_rows(START, END, filters)
    return _generic_groups(rows), totals


@pytest.fixture
def two_strengths(owner, supplier, customer, client_settings):
    """One generic, two strengths, sold to the same customer."""
    small = _item("AMOX250", "Amoxil", "amoxicillin", "250 mg")
    large = _item("AMOX500", "Amoxil", "amoxicillin", "500 mg")
    other = _item("PARA", "Panadol", "paracetamol", "500 mg")
    for item, cost in ((small, "4.00"), (large, "10.00"), (other, "4.00")):
        receive(owner, supplier, item, qty=100, cost=cost)
    credit_sale(owner, customer, small, qty=10, price="6.00")
    credit_sale(owner, customer, large, qty=10, price="20.00")
    credit_sale(owner, customer, other, qty=5, price="6.00")
    return small, large, other


def test_two_strengths_of_one_generic_become_one_group(two_strengths):
    groups, _totals = _groups()
    labels = [group["label"] for group in groups]
    assert labels == ["amoxicillin", "paracetamol"]
    assert len(groups[0]["lines"]) == 2


def test_the_group_adds_up_the_money(two_strengths):
    groups, _totals = _groups()
    amox = groups[0]
    assert amox["revenue"] == D("260.00")   # 60 + 200
    assert amox["cogs"] == D("140.00")      # 40 + 100
    assert amox["profit"] == D("120.00")


def test_the_group_does_not_add_up_the_quantity(two_strengths):
    """D132: 10 of 250 mg plus 10 of 500 mg is not 20 of anything."""
    groups, _totals = _groups()
    assert groups[0]["qty"] is None
    # The lines inside still carry their own.
    assert sorted(line["qty"] for line in groups[0]["lines"]) == [10, 10]


def test_grouping_never_changes_the_total(two_strengths):
    groups, totals = _groups()
    assert sum(group["revenue"] for group in groups) == totals["revenue"]
    assert sum(group["cogs"] for group in groups) == totals["cogs"]


def test_each_line_inside_a_group_still_names_its_document(two_strengths):
    groups, _totals = _groups()
    line = groups[0]["lines"][0]
    assert line["doc_no"].startswith("SI-")
    assert line["doc_pk"]
    assert line["brand"] == "Amoxil"
    assert line["strength"] in ("250 mg", "500 mg")


def test_spelling_and_case_fold_into_one_group(owner, supplier, customer,
                                               client_settings):
    """D126's rule, unchanged: case and surrounding space are provably the
    same generic; a real misspelling is not."""
    first = _item("A1", "Brand one", "  Amoxicillin ", "250 mg")
    second = _item("A2", "Brand two", "amoxicillin", "500 mg")
    for item in (first, second):
        receive(owner, supplier, item, qty=50)
    credit_sale(owner, customer, first, qty=1)
    credit_sale(owner, customer, second, qty=1)

    groups, _totals = _groups()
    assert len(groups) == 1
    assert groups[0]["label"] == "Amoxicillin"   # the commonest spelling wins


def test_the_split_matches_sales_by_generic(two_strengths, owner):
    """The two reports must never disagree about what one generic is."""
    from reports.views import REPORTS
    _cols, rows, _total = REPORTS["sales-by-generic"]["builder"](START, END, owner)
    groups, _totals = _groups()
    assert [row[0] for row in rows] == [group["label"] for group in groups]


def test_an_item_with_no_generic_gets_its_own_group(owner, supplier, customer):
    item = _item("SUP", "Gloves")
    receive(owner, supplier, item, qty=10)
    credit_sale(owner, customer, item, qty=2)

    groups, _totals = _groups()
    assert groups[0]["label"] == "(no generic set)"


def test_charges_and_discounts_form_their_own_group_at_the_end(owner, supplier,
                                                               customer):
    """R75: they belong to the invoice, not to a generic, and dropping them
    would make the grouped total disagree with the ungrouped one."""
    item = _item("AMOX", "Amoxil", "amoxicillin", "500 mg")
    receive(owner, supplier, item, qty=10)
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                  customer=customer,
                                  sale_kind=Document.SaleKind.CREDIT,
                                  due_date=datetime.date(2029, 1, 1))
    DocumentLine.objects.create(document=doc, item=item,
                                batch=Batch.objects.get(item=item),
                                qty_entered=2, unit_price=D("15.00"),
                                unit_label="pack", factor=1)
    DocumentCharge.objects.create(document=doc, label="Delivery",
                                  amount=D("50.00"), is_taxable=False)
    post(doc, owner)

    groups, totals = _groups()
    assert [group["label"] for group in groups] == [
        "amoxicillin", "Other charges and discounts"]
    assert groups[-1]["revenue"] == D("50.00")
    assert sum(group["revenue"] for group in groups) == totals["revenue"]


def test_a_filter_applies_before_the_grouping(two_strengths):
    groups, totals = _groups(brand="panadol")
    assert [group["label"] for group in groups] == ["paracetamol"]
    assert totals["revenue"] == D("30.00")


# --- the page -------------------------------------------------------------

def test_the_page_offers_the_grouping(client, owner, two_strengths):
    client.force_login(owner)
    content = client.get(reverse("sales_report")).content.decode()
    assert 'name="group"' in content
    assert "Generic" in content


def test_grouping_renders_one_row_per_generic(client, owner, two_strengths):
    client.force_login(owner)
    response = client.get(reverse("sales_report"), {"group": "generic"})
    content = response.content.decode()
    assert "amoxicillin" in content
    assert "260.00" in content       # the group total, not a line
    assert "<details" in content     # the lines are still reachable


def test_an_employee_grouping_sees_no_cost_or_profit(client, staff, two_strengths):
    client.force_login(staff)
    content = client.get(reverse("sales_report"),
                         {"group": "generic"}).content.decode()
    assert "COGS" not in content
    assert "Profit" not in content


def test_the_grouped_csv_exports_the_groups(client, owner, two_strengths):
    client.force_login(owner)
    body = client.get(reverse("sales_report"),
                      {"group": "generic", "format": "csv"}).content.decode()
    lines = [line for line in body.splitlines() if line.strip()]
    assert lines[0].startswith("Generic")
    assert any(line.startswith("amoxicillin") and "260.00" in line
               for line in lines)
    assert lines[-1].startswith("Total")
