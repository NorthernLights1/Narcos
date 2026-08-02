"""D94/D95 — voiding an invoice must take its payment with it.

Before D95, voiding a settled invoice reversed only what the invoice
itself wrote. The receipt was a separate document and stayed posted, so
the customer was left at −200.00 (the business owing them) with an
allocation pointing at a document that no longer existed.

D94 makes one receipt settle exactly one invoice, which makes the D95
cascade unambiguous: there is never a second invoice hanging off the
receipt being reversed.
"""

import datetime
from decimal import Decimal

import pytest
from django.db.models import Sum

from catalog.models import Account, Customer, Item, Supplier
from docs.models import Document, DocType, DocumentLine
from docs.posting import PostingError, post, void
from money.models import PaymentAllocation, PaymentLine, PartyLedger
from stock.models import Batch

pytestmark = pytest.mark.django_db

D = Decimal
FAR = datetime.date(2030, 1, 1)
DUE = datetime.date(2026, 12, 31)


def _balance(customer) -> Decimal:
    return PartyLedger.objects.filter(
        party_type="CUSTOMER", party_id=customer.pk
    ).aggregate(s=Sum("amount_delta"))["s"] or D("0.00")


@pytest.fixture
def customer():
    return Customer.objects.create(code="C001", name="Selam Pharmacy")


@pytest.fixture
def cash():
    return Account.objects.create(name="Cash drawer", type=Account.Type.CASH)


@pytest.fixture
def stocked_item(owner):
    supplier = Supplier.objects.create(code="S001", name="Addis Pharma")
    item = Item.objects.create(code="AMOX", name="Amoxicillin",
                               base_unit="pack", is_batch_tracked=True,
                               has_expiry=True, vat_exempt=True,
                               maintained_price=D("100.00"))
    grn = Document.objects.create(doc_type=DocType.RECEIVING,
                                  created_by=owner, supplier=supplier)
    DocumentLine.objects.create(
        document=grn, item=item, qty_entered=20, unit_cost_entered=D("50.00"),
        batch_no_entered="B-1", expiry_entered=FAR, unit_label="pack", factor=1,
    )
    post(grn, owner)
    return item


def _credit_sale(owner, customer, item, qty=2):
    sale = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                   customer=customer, due_date=DUE,
                                   sale_kind=Document.SaleKind.CREDIT)
    DocumentLine.objects.create(
        document=sale, item=item, batch=Batch.objects.get(item=item),
        qty_entered=qty, unit_price=D("100.00"), unit_label="pack", factor=1,
    )
    return post(sale, owner)


def _receipt(owner, customer, cash, targets: dict):
    """targets: {invoice: amount}"""
    rc = Document.objects.create(doc_type=DocType.CUSTOMER_PAYMENT,
                                 created_by=owner, customer=customer)
    total = sum(targets.values(), D("0.00"))
    PaymentLine.objects.create(document=rc, account=cash, amount=total)
    for target, amount in targets.items():
        PaymentAllocation.objects.create(payment=rc, target=target, amount=amount)
    return rc


# --- D94: one receipt, one invoice ---------------------------------------

def test_a_receipt_may_settle_one_invoice(owner, customer, cash, stocked_item):
    sale = _credit_sale(owner, customer, stocked_item)
    rc = _receipt(owner, customer, cash, {sale: D("200.00")})
    post(rc, owner)
    assert _balance(customer) == D("0.00")


def test_a_receipt_may_not_settle_two_invoices(owner, customer, cash,
                                               stocked_item):
    first = _credit_sale(owner, customer, stocked_item)
    second = _credit_sale(owner, customer, stocked_item)
    rc = _receipt(owner, customer, cash,
                  {first: D("200.00"), second: D("200.00")})
    with pytest.raises(PostingError, match="one invoice"):
        post(rc, owner)


# --- D95: the void takes the money with it --------------------------------

def test_voiding_a_settled_invoice_reverses_its_receipt(owner, customer, cash,
                                                        stocked_item):
    sale = _credit_sale(owner, customer, stocked_item)
    rc = post(_receipt(owner, customer, cash, {sale: D("200.00")}), owner)
    assert _balance(customer) == D("0.00")

    void(sale, owner, "wrong quantity")

    rc.refresh_from_db()
    assert rc.status == Document.Status.VOIDED
    assert _balance(customer) == D("0.00")   # not −200: the money went back


def test_the_receipt_records_why_it_was_reversed(owner, customer, cash,
                                                 stocked_item):
    sale = _credit_sale(owner, customer, stocked_item)
    rc = post(_receipt(owner, customer, cash, {sale: D("200.00")}), owner)
    void(sale, owner, "wrong quantity")
    rc.refresh_from_db()
    assert "wrong quantity" in rc.void_reason
    assert sale.doc_no in rc.void_reason


def test_an_unpaid_invoice_voids_without_touching_anything(owner, customer,
                                                           stocked_item):
    sale = _credit_sale(owner, customer, stocked_item)
    assert _balance(customer) == D("200.00")
    void(sale, owner, "cancelled order")
    assert _balance(customer) == D("0.00")


def test_an_already_voided_receipt_is_not_voided_twice(owner, customer, cash,
                                                       stocked_item):
    sale = _credit_sale(owner, customer, stocked_item)
    rc = post(_receipt(owner, customer, cash, {sale: D("200.00")}), owner)
    void(rc, owner, "wrong receipt")     # owner reverses the payment first
    rc.refresh_from_db()
    assert rc.status == Document.Status.VOIDED

    void(sale, owner, "then the invoice")   # must not fail on the dead receipt

    assert _balance(customer) == D("0.00")


def test_correcting_a_paid_sale_leaves_the_books_flat(client, owner, customer,
                                                      cash, stocked_item):
    """D92 + D95 together: the workflow that made this urgent."""
    from django.urls import reverse
    sale = _credit_sale(owner, customer, stocked_item)
    post(_receipt(owner, customer, cash, {sale: D("200.00")}), owner)
    client.force_login(owner)

    client.post(reverse("document_correct", args=[sale.pk]),
                {"reason": "wrong quantity"})
    draft = Document.objects.get(doc_type=DocType.SALE,
                                 status=Document.Status.DRAFT)
    client.post(reverse("document_post", args=[draft.pk]))

    sale.refresh_from_db()
    draft.refresh_from_db()
    assert sale.status == Document.Status.VOIDED
    assert draft.status == Document.Status.POSTED
    # The replacement is unpaid, so the customer owes it — and only it.
    assert _balance(customer) == D("200.00")


# --- D96: a sale takes its customer return with it ------------------------

def _return_against(owner, sale, item, qty=2):
    from stock.models import Zone
    cr = Document.objects.create(doc_type=DocType.CUSTOMER_RETURN,
                                 created_by=owner, customer=sale.customer,
                                 related_document=sale)
    DocumentLine.objects.create(
        document=cr, item=item, batch=Batch.objects.get(item=item),
        qty_entered=qty, unit_price=D("100.00"), target_zone=Zone.WAREHOUSE,
        unit_label="pack", factor=1,
    )
    return post(cr, owner)


def _warehouse(item) -> int:
    from stock.models import StockBalance, Zone
    return StockBalance.objects.filter(
        zone=Zone.WAREHOUSE, lot__item=item
    ).aggregate(s=Sum("qty"))["s"] or 0


def test_voiding_a_sale_reverses_its_customer_return(owner, customer,
                                                     stocked_item):
    """Before D96 this left the customer at −200.00 *and* invented two
    packs of stock: the return handed goods back against a sale that no
    longer existed."""
    before = _warehouse(stocked_item)
    sale = _credit_sale(owner, customer, stocked_item, qty=5)
    cr = _return_against(owner, sale, stocked_item, qty=2)
    assert _balance(customer) == D("300.00")

    void(sale, owner, "wrong order")

    cr.refresh_from_db()
    assert cr.status == Document.Status.VOIDED
    assert _balance(customer) == D("0.00")      # not −200.00
    assert _warehouse(stocked_item) == before   # no phantom packs


def test_an_already_voided_return_is_not_voided_twice(owner, customer,
                                                      stocked_item):
    before = _warehouse(stocked_item)
    sale = _credit_sale(owner, customer, stocked_item, qty=5)
    cr = _return_against(owner, sale, stocked_item, qty=2)
    void(cr, owner, "return keyed twice")

    void(sale, owner, "and now the sale")

    assert _balance(customer) == D("0.00")
    assert _warehouse(stocked_item) == before


# --- D97: a settled consignment issue says so ----------------------------

def test_voiding_a_settled_issue_explains_itself(owner, customer,
                                                 stocked_item):
    """It was already refused — but by the stock rule, so the owner got
    'Not enough stock … in CONSIGNED (have 0, need 10)'."""
    issue = Document.objects.create(doc_type=DocType.CONSIGNMENT_ISSUE,
                                    created_by=owner, customer=customer,
                                    due_date=DUE)
    DocumentLine.objects.create(
        document=issue, item=stocked_item, batch=Batch.objects.get(item=stocked_item),
        qty_entered=10, unit_price=D("100.00"), unit_label="pack", factor=1,
    )
    post(issue, owner)
    settlement = Document.objects.create(
        doc_type=DocType.CONSIGNMENT_SETTLEMENT, created_by=owner,
        customer=customer, related_document=issue, sale_kind="CREDIT",
        due_date=DUE,
    )
    DocumentLine.objects.create(
        document=settlement, item=stocked_item,
        batch=Batch.objects.get(item=stocked_item),
        qty_entered=10, qty_sold=6, qty_returned=4, unit_label="pack", factor=1,
    )
    post(settlement, owner)

    with pytest.raises(PostingError, match="settle"):
        void(issue, owner, "changed my mind")
