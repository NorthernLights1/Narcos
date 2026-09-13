"""D141: the sales report, with the item named and the document reachable.

The client likes this report and asked for four things: a document number you
can click, the generic and the brand beside the code, per-item money, and
filters for document, generic and brand.

Per-item money was already true — `ITM-0005 · 120 · 43,200.00` is that line's
quantity and that line's revenue, and the six lines of `SI-000005` sum to its
grand total. What the report did not do was *say* which item a row was: the
Item column held a bare code, so the row read as if the money belonged to the
invoice. Naming the item is the fix; the arithmetic did not change.
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
from reports.views import _sale_line_rows
from stock.models import Batch, Zone

pytestmark = pytest.mark.django_db

D = Decimal
START, END = datetime.date(2000, 1, 1), datetime.date(2030, 1, 1)
FAR_EXPIRY = datetime.date(2030, 1, 1)


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
    """The configuration the client actually runs: no sales tax at all, and
    the counter types its own prices (D89). Revenue on this report is net of
    tax either way; with the regime off, net revenue IS the invoice total,
    which is what makes the per-line tie-out below readable."""
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


def _rows(start=START, end=END, **filters):
    return _sale_line_rows(start, end, filters)


def _page(client, user, **params):
    client.force_login(user)
    return client.get(reverse("sales_report"), params)


# --- what a row is --------------------------------------------------------

def test_each_row_carries_its_own_line_not_the_document(owner, supplier,
                                                        customer, client_settings):
    """Two items on one invoice: two rows, each with its own money."""
    amox = _item("AMOX", "Amoxil", "amoxicillin", "500 mg")
    para = _item("PARA", "Panadol", "paracetamol", "500 mg")
    receive(owner, supplier, amox, qty=100, cost="10.00")
    receive(owner, supplier, para, qty=100, cost="4.00")
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                  customer=customer,
                                  sale_kind=Document.SaleKind.CREDIT,
                                  due_date=datetime.date(2029, 1, 1))
    for item, qty, price in ((amox, 3, "20.00"), (para, 5, "6.00")):
        DocumentLine.objects.create(
            document=doc, item=item, batch=Batch.objects.get(item=item),
            qty_entered=qty, unit_price=D(price), unit_label="pack", factor=1)
    doc = post(doc, owner)

    rows, totals = _rows()
    assert [(r["code"], r["qty"], r["revenue"], r["cogs"]) for r in rows] == [
        ("AMOX", 3, D("60.00"), D("30.00")),
        ("PARA", 5, D("30.00"), D("20.00")),
    ]
    assert totals["revenue"] == D("90.00")
    assert sum(r["revenue"] for r in rows) == doc.grand_total


def test_a_row_names_the_generic_the_brand_and_the_strength(owner, supplier,
                                                            customer):
    item = _item("AMOX", "Amoxil", "amoxicillin", "500 mg")
    receive(owner, supplier, item, qty=10)
    credit_sale(owner, customer, item, qty=2)

    row = _rows()[0][0]
    assert row["code"] == "AMOX"
    assert row["generic"] == "amoxicillin"
    assert row["brand"] == "Amoxil"
    assert row["strength"] == "500 mg"


def test_the_row_knows_which_document_to_open(owner, supplier, customer):
    item = _item("AMOX", "Amoxil")
    receive(owner, supplier, item, qty=10)
    sale = credit_sale(owner, customer, item, qty=2)

    row = _rows()[0][0]
    assert row["doc_no"] == sale.doc_no
    assert row["doc_pk"] == sale.pk


def test_the_page_links_every_document_number(client, owner, supplier, customer):
    item = _item("AMOX", "Amoxil")
    receive(owner, supplier, item, qty=10)
    sale = credit_sale(owner, customer, item, qty=2)

    content = _page(client, owner).content.decode()
    assert reverse("document_detail", args=[sale.pk]) in content
    assert sale.doc_no in content


def test_a_return_reads_as_negative(owner, supplier, customer):
    item = _item("AMOX", "Amoxil")
    receive(owner, supplier, item, qty=10)
    sale = credit_sale(owner, customer, item, qty=4)
    line = sale.lines.first()
    ret = Document.objects.create(doc_type=DocType.CUSTOMER_RETURN,
                                  created_by=owner, customer=customer,
                                  related_document=sale)
    DocumentLine.objects.create(document=ret, item=item, batch=line.batch,
                                lot=line.lot_consumptions.first().lot,
                                qty_entered=1, unit_price=line.unit_price,
                                unit_label="pack", factor=1,
                                target_zone=Zone.WAREHOUSE)
    ret = post(ret, owner)

    rows, totals = _rows()
    returned = [r for r in rows if r["doc_no"] == ret.doc_no]
    assert len(returned) == 1
    assert returned[0]["qty"] < 0
    assert returned[0]["revenue"] < 0
    assert totals["revenue"] == D("45.00")


# --- R75: money that belongs to the document, not to an item --------------

def test_a_delivery_charge_is_its_own_row_with_no_item(owner, supplier,
                                                       customer):
    item = _item("AMOX", "Amoxil", "amoxicillin")
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
    doc = post(doc, owner)

    rows, totals = _rows()
    extras = [r for r in rows if r["is_extra"]]
    assert len(extras) == 1
    assert extras[0]["label"] == "Delivery"
    assert extras[0]["revenue"] == D("50.00")
    assert extras[0]["qty"] is None
    assert totals["revenue"] == D("80.00")


def test_a_charge_drops_out_when_the_filter_names_a_brand(owner, supplier,
                                                          customer):
    """A delivery fee belongs to no brand, so it cannot answer a question
    about one — and leaving it in would inflate that brand's revenue."""
    item = _item("AMOX", "Amoxil", "amoxicillin")
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
    doc = post(doc, owner)

    rows, totals = _rows(brand="amoxil")
    assert [r["is_extra"] for r in rows] == [False]
    assert totals["revenue"] == D("30.00")
    # The same charge still shows when the question is about the document.
    rows, _totals = _rows(doc=doc.doc_no)
    assert [r["is_extra"] for r in rows] == [False, True]


# --- the three filters ----------------------------------------------------

@pytest.fixture
def two_sales(owner, supplier, customer, client_settings):
    amox = _item("AMOX", "Amoxil", "amoxicillin", "500 mg")
    para = _item("PARA", "Panadol", "paracetamol", "500 mg")
    receive(owner, supplier, amox, qty=100, cost="10.00")
    receive(owner, supplier, para, qty=100, cost="4.00")
    first = credit_sale(owner, customer, amox, qty=2, price="20.00")
    second = credit_sale(owner, customer, para, qty=5, price="6.00")
    return first, second


def test_filtering_by_document_number_keeps_only_that_document(two_sales):
    first, _second = two_sales
    rows, totals = _rows(doc=first.doc_no)
    assert {r["doc_no"] for r in rows} == {first.doc_no}
    assert totals["revenue"] == D("40.00")


def test_the_document_filter_matches_part_of_the_number(two_sales):
    first, _second = two_sales
    rows, _totals = _rows(doc=first.doc_no[-3:])
    assert {r["doc_no"] for r in rows} == {first.doc_no}


def test_filtering_by_generic_ignores_case_and_matches_part(two_sales):
    rows, totals = _rows(generic="ParaCet")
    assert {r["brand"] for r in rows} == {"Panadol"}
    assert totals["revenue"] == D("30.00")


def test_filtering_by_brand_ignores_case_and_matches_part(two_sales):
    rows, totals = _rows(brand="amox")
    assert {r["generic"] for r in rows} == {"amoxicillin"}
    assert totals["revenue"] == D("40.00")


def test_the_filters_combine(two_sales):
    first, _second = two_sales
    assert _rows(doc=first.doc_no, brand="panadol")[0] == []


def test_the_total_and_the_profit_follow_the_filter(two_sales):
    rows, totals = _rows(brand="panadol")
    assert totals["revenue"] == D("30.00")
    assert totals["cogs"] == D("20.00")
    assert totals["profit"] == D("10.00")
    assert len(rows) == 1


def test_a_filter_that_matches_nothing_says_so(client, owner, two_sales):
    response = _page(client, owner, brand="nothing-like-this")
    assert response.status_code == 200
    assert b"No rows." in response.content


# --- who may see cost -----------------------------------------------------

def test_an_employee_sees_revenue_but_not_cost_or_profit(client, staff,
                                                         two_sales):
    content = _page(client, staff).content.decode()
    assert "Revenue" in content
    assert "COGS" not in content
    assert "Profit" not in content


def test_the_owner_sees_cost_and_profit(client, owner, two_sales):
    content = _page(client, owner).content.decode()
    assert "COGS" in content
    assert "Profit" in content


# --- CSV ------------------------------------------------------------------

def test_the_csv_carries_the_filtered_rows(client, owner, two_sales):
    client.force_login(owner)
    response = client.get(reverse("sales_report"),
                          {"format": "csv", "brand": "panadol"})
    body = response.content.decode()
    assert response["Content-Type"] == "text/csv"
    assert "Panadol" in body
    assert "Amoxil" not in body
    assert "paracetamol" in body


# --- the hub --------------------------------------------------------------

def test_the_hub_offers_it(client, owner):
    client.force_login(owner)
    content = client.get(reverse("report_hub")).content.decode()
    assert reverse("sales_report") in content


def test_the_sales_log_is_gone(client, owner):
    """D141 withdrew D138 — the client asked for one sales report, not two."""
    client.force_login(owner)
    content = client.get(reverse("report_hub")).content.decode()
    assert "Sales log" not in content
    assert client.get("/reports/sales-log/").status_code == 404
