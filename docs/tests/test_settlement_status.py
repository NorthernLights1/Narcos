"""D73 settlement visibility: derived Unpaid/Partial/Settled (money) and
Open/Partial/Closed (consignment qty) states, the transactions-list filter,
the detail-page settlement card, and open-item reports that ignore the
period filter."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Customer, Item, Supplier
from docs.models import Document, DocType, DocumentLine
from docs.posting import post, void
from docs.settlement import annotate_settlement, settlement_state
from money.models import PaymentAllocation, PaymentLine
from stock.models import Batch

pytestmark = pytest.mark.django_db

D = Decimal
FAR_EXPIRY = datetime.date(2030, 1, 1)


@pytest.fixture
def customer(db):
    return Customer.objects.create(code="C001", name="Mekelle Hospital PLC")


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(code="S001", name="Addis Pharma")


@pytest.fixture
def item(db):
    return Item.objects.create(code="KIT", name="Test kit", base_unit="kit",
                               is_batch_tracked=True, has_expiry=True,
                               vat_exempt=True)


def receive(actor, supplier, item, qty=100, cost="10.00"):
    doc = Document.objects.create(doc_type=DocType.RECEIVING, created_by=actor,
                                  supplier=supplier)
    DocumentLine.objects.create(document=doc, item=item, qty_entered=qty,
                                unit_cost_entered=D(cost), batch_no_entered="B-1",
                                expiry_entered=FAR_EXPIRY, unit_label="kit", factor=1)
    return post(doc, actor)


def credit_sale(actor, customer, item, qty=100, price="15.00"):
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=actor,
                                  customer=customer, sale_kind="CREDIT",
                                  due_date=datetime.date(2026, 8, 1))
    DocumentLine.objects.create(document=doc, item=item, batch=Batch.objects.get(),
                                qty_entered=qty, unit_price=D(price),
                                unit_label="kit", factor=1)
    return post(doc, actor)


def pay(actor, customer, target, amount, account):
    doc = Document.objects.create(doc_type=DocType.CUSTOMER_PAYMENT,
                                  created_by=actor, customer=customer)
    PaymentLine.objects.create(document=doc, account=account, amount=D(amount))
    PaymentAllocation.objects.create(payment=doc, target=target, amount=D(amount))
    return post(doc, actor)


def consignment_issue(actor, customer, item, qty=5, price="100.00"):
    doc = Document.objects.create(doc_type=DocType.CONSIGNMENT_ISSUE,
                                  created_by=actor, customer=customer)
    DocumentLine.objects.create(document=doc, item=item, batch=Batch.objects.get(),
                                qty_entered=qty, unit_price=D(price),
                                unit_label="kit", factor=1)
    return post(doc, actor)


def settle(actor, customer, issue, sold=0, returned=0):
    doc = Document.objects.create(doc_type=DocType.CONSIGNMENT_SETTLEMENT,
                                  created_by=actor, customer=customer,
                                  related_document=issue, sale_kind="CREDIT")
    DocumentLine.objects.create(document=doc, item=issue.lines.get().item,
                                batch=Batch.objects.get(),
                                qty_entered=sold + returned, qty_sold=sold,
                                qty_returned=returned, unit_label="kit", factor=1)
    return post(doc, actor)


# --- settlement_state (money) ---


def test_credit_sale_walks_unpaid_partial_settled(owner, customer, supplier,
                                                  item, cash):
    receive(owner, supplier, item)
    sale = credit_sale(owner, customer, item)  # 1500 AR
    state = settlement_state(sale)
    assert state == {"kind": "money", "state": "UNPAID", "label": "Unpaid",
                     "total": D("1500.00"), "settled": D("0.00"),
                     "open": D("1500.00")}

    pay(owner, customer, sale, "600.00", cash)
    state = settlement_state(sale)
    assert state["state"] == "PARTIAL"
    assert state["settled"] == D("600.00")
    assert state["open"] == D("900.00")

    pay(owner, customer, sale, "900.00", cash)
    assert settlement_state(sale)["state"] == "SETTLED"


def test_voided_payment_reopens_the_invoice_state(owner, customer, supplier,
                                                  item, cash):
    receive(owner, supplier, item)
    sale = credit_sale(owner, customer, item)
    rc = pay(owner, customer, sale, "1500.00", cash)
    assert settlement_state(sale)["state"] == "SETTLED"
    void(rc, owner, "wrong customer")
    state = settlement_state(sale)
    assert state["state"] == "UNPAID"
    assert state["open"] == D("1500.00")


def test_cash_sale_and_drafts_have_no_settlement_state(owner, customer,
                                                       supplier, item, cash):
    receive(owner, supplier, item)
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                  customer=customer, sale_kind="CASH")
    DocumentLine.objects.create(document=doc, item=item, batch=Batch.objects.get(),
                                qty_entered=1, unit_price=D("15.00"),
                                unit_label="kit", factor=1)
    assert settlement_state(doc) is None  # draft
    PaymentLine.objects.create(document=doc, account=cash, amount=D("15.00"))
    doc = post(doc, owner)
    assert settlement_state(doc) is None  # cash: auto payment settles it


def test_receiving_carries_ap_settlement_state(owner, supplier, item):
    grn = receive(owner, supplier, item)  # 1000 AP
    state = settlement_state(grn)
    assert state["state"] == "UNPAID"
    assert state["open"] == D("1000.00")


# --- settlement_state (consignment qty) ---


def test_consignment_issue_walks_open_partial_closed(owner, customer,
                                                     supplier, item):
    receive(owner, supplier, item)
    cn = consignment_issue(owner, customer, item, qty=5)
    state = settlement_state(cn)
    assert state == {"kind": "qty", "state": "OPEN", "label": "Open",
                     "issued": 5, "settled": 0, "open": 5}

    settle(owner, customer, cn, sold=2)
    state = settlement_state(cn)
    assert state["state"] == "PARTIAL"
    assert state["open"] == 3

    settle(owner, customer, cn, sold=1, returned=2)
    assert settlement_state(cn)["state"] == "CLOSED"


# --- the annotated list path must agree with the per-document path ---


def test_annotated_state_matches_fallback_state(owner, customer, supplier,
                                                item, cash):
    receive(owner, supplier, item)
    sale = credit_sale(owner, customer, item, qty=10)  # 150 AR
    pay(owner, customer, sale, "60.00", cash)
    cn = consignment_issue(owner, customer, item, qty=5)
    settle(owner, customer, cn, sold=2)
    for doc in annotate_settlement(Document.objects.all()):
        plain = Document.objects.get(pk=doc.pk)
        assert settlement_state(doc) == settlement_state(plain), doc


# --- transactions list: badge and outstanding filter ---


def test_list_filters_outstanding_and_settled(client, owner, customer,
                                              supplier, item, cash):
    receive(owner, supplier, item)
    open_sale = credit_sale(owner, customer, item, qty=10)  # 150, unpaid
    paid_sale = credit_sale(owner, customer, item, qty=20)  # 300, paid below
    pay(owner, customer, paid_sale, "300.00", cash)
    client.force_login(owner)

    response = client.get(reverse("document_list"),
                          {"settlement": "open", "type": DocType.SALE})
    content = response.content.decode()
    assert open_sale.doc_no in content
    assert paid_sale.doc_no not in content

    response = client.get(reverse("document_list"),
                          {"settlement": "settled", "type": DocType.SALE})
    content = response.content.decode()
    assert paid_sale.doc_no in content
    assert open_sale.doc_no not in content


def test_list_shows_partial_open_amounts(client, owner, customer, supplier,
                                         item, cash):
    receive(owner, supplier, item)
    sale = credit_sale(owner, customer, item)  # 1500
    pay(owner, customer, sale, "600.00", cash)
    client.force_login(owner)
    response = client.get(reverse("document_list"), {"type": DocType.SALE})
    content = response.content.decode()
    assert "Partial" in content
    assert "900.00" in content  # open ... of 1500.00


# --- detail page: settlement card ---


def test_invoice_detail_shows_outstanding_and_allocation_history(
        client, owner, customer, supplier, item, cash):
    receive(owner, supplier, item)
    sale = credit_sale(owner, customer, item)  # 1500
    rc = pay(owner, customer, sale, "600.00", cash)
    client.force_login(owner)
    content = client.get(reverse("document_detail", args=[sale.pk])).content.decode()
    assert "Settled to date" in content
    assert "600.00" in content
    assert "Outstanding" in content
    assert "900.00" in content
    assert rc.doc_no in content  # allocation history links the payment


def test_payment_detail_shows_what_it_settled(client, owner, customer,
                                              supplier, item, cash):
    receive(owner, supplier, item)
    sale = credit_sale(owner, customer, item)
    rc = pay(owner, customer, sale, "600.00", cash)
    client.force_login(owner)
    content = client.get(reverse("document_detail", args=[rc.pk])).content.decode()
    assert "Allocated to" in content
    assert sale.doc_no in content


def test_issue_detail_shows_still_out_and_settlements(client, owner, customer,
                                                      supplier, item):
    receive(owner, supplier, item)
    cn = consignment_issue(owner, customer, item, qty=5)
    cs = settle(owner, customer, cn, sold=2)
    client.force_login(owner)
    content = client.get(reverse("document_detail", args=[cn.pk])).content.decode()
    assert "Still out" in content
    assert cs.doc_no in content


# --- open-item reports ignore the period filter (D73) ---


def test_aging_report_keeps_old_unpaid_invoices_visible(owner, customer,
                                                        supplier, item):
    from reports.views import _ar_aging

    receive(owner, supplier, item)
    sale = credit_sale(owner, customer, item)
    # A range far in the past must not hide the open invoice
    ancient = datetime.date(1990, 1, 1)
    columns, rows, _total = _ar_aging(ancient, ancient, owner)
    assert len(rows) == 1
    row = rows[0]
    assert row[2] == sale.doc_no
    assert row[4] == D("1500.00")  # original
    assert row[5] == D("0.00")  # settled
    assert row[6] == D("1500.00")  # open


def test_consignment_report_keeps_old_open_issues_visible(owner, customer,
                                                          supplier, item):
    from reports.views import _consignment

    receive(owner, supplier, item)
    cn = consignment_issue(owner, customer, item, qty=5)
    settle(owner, customer, cn, sold=2)
    ancient = datetime.date(1990, 1, 1)
    _columns, rows, _total = _consignment(ancient, ancient, owner)
    assert len(rows) == 1
    assert rows[0][2] == cn.doc_no
    assert rows[0][4] == 3  # remaining qty
