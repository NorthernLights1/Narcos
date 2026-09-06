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


def test_correcting_a_paid_sale_is_refused(client, owner, customer,
                                           cash, stocked_item):
    """R70: D92 and D95 together used to lose the customer's money.

    Correcting voided the sale, D95 took the receipt with it, and the
    replacement carried no receipt — so the 200.00 the customer had actually
    handed over left the books and they were billed for it a second time.
    The correction is refused now; void the receipt first, then correct.
    """
    from django.urls import reverse
    sale = _credit_sale(owner, customer, stocked_item)
    receipt = post(_receipt(owner, customer, cash, {sale: D("200.00")}), owner)
    client.force_login(owner)

    response = client.post(reverse("document_correct", args=[sale.pk]),
                           {"reason": "wrong quantity"})

    sale.refresh_from_db()
    receipt.refresh_from_db()
    assert sale.status == Document.Status.POSTED
    assert receipt.status == Document.Status.POSTED
    assert not Document.objects.filter(corrects=sale).exists()
    assert _balance(customer) == D("0.00")       # settled, and it stays settled
    assert response.status_code == 302
    assert response.url == reverse("document_detail", args=[sale.pk])


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


# --- D99: the withheld tax was already handed to the tax office -----------

def _payable() -> Decimal:
    from money.models import WithholdingLedger
    return WithholdingLedger.objects.filter(direction="PAYABLE").aggregate(
        s=Sum("amount_delta"))["s"] or D("0.00")


@pytest.fixture
def withholding_on(db):
    from core.models import CompanySettings
    settings = CompanySettings.load()
    settings.withholding_on_purchases = True
    settings.save()
    return settings


def _receiving(owner, item):
    """The GRN behind `stocked_item`: 20 packs at 50.00 → AP 1000.00."""
    return Document.objects.get(doc_type=DocType.RECEIVING,
                                status=Document.Status.POSTED)


def _supplier_payment(owner, grn, cash, withheld=D("30.00")):
    """Pay the 1000 AP as 970 cash + 30 kept back for the tax office."""
    pv = Document.objects.create(doc_type=DocType.SUPPLIER_PAYMENT,
                                 created_by=owner, supplier=grn.supplier,
                                 withheld_amount=withheld)
    PaymentLine.objects.create(document=pv, account=cash,
                               amount=grn.grand_total - withheld)
    PaymentAllocation.objects.create(payment=pv, target=grn,
                                     amount=grn.grand_total)
    return post(pv, owner)


def _remit(owner, cash, amount=D("30.00")):
    wr = Document.objects.create(doc_type=DocType.WHT_REMITTANCE, created_by=owner)
    PaymentLine.objects.create(document=wr, account=cash, amount=amount)
    return post(wr, owner)


def test_voiding_a_remitted_payment_is_refused(owner, cash, stocked_item,
                                               withholding_on):
    """The 30.00 kept back from the supplier has already been paid to the
    tax office. Reversing the payment alone pushes PAYABLE to −30.00: the
    business is out 30.00 with nothing in the books to show for it."""
    grn = _receiving(owner, stocked_item)
    pv = _supplier_payment(owner, grn, cash)
    assert _payable() == D("30.00")
    _remit(owner, cash)
    assert _payable() == D("0.00")

    with pytest.raises(PostingError, match="tax office"):
        void(pv, owner, "paid the wrong supplier")

    pv.refresh_from_db()
    assert pv.status == Document.Status.POSTED
    assert _payable() == D("0.00")      # not −30.00


def test_voiding_the_invoice_behind_a_remitted_payment_is_refused(
        owner, cash, stocked_item, withholding_on):
    """Same hole reached through the D95 cascade: voiding the receiving
    drags the payment down with it, remitted withholding and all."""
    grn = _receiving(owner, stocked_item)
    _supplier_payment(owner, grn, cash)
    _remit(owner, cash)

    with pytest.raises(PostingError, match="tax office"):
        void(grn, owner, "wrong goods")

    grn.refresh_from_db()
    assert grn.status == Document.Status.POSTED
    assert _payable() == D("0.00")


def test_voiding_the_remittance_first_then_the_payment_works(
        owner, cash, stocked_item, withholding_on):
    """The way out the message points at."""
    grn = _receiving(owner, stocked_item)
    pv = _supplier_payment(owner, grn, cash)
    wr = _remit(owner, cash)

    void(wr, owner, "remitted too early")
    assert _payable() == D("30.00")
    void(pv, owner, "paid the wrong supplier")

    assert _payable() == D("0.00")


def test_an_unremitted_payment_still_voids(owner, cash, stocked_item,
                                           withholding_on):
    """The guard must not block the ordinary case."""
    grn = _receiving(owner, stocked_item)
    pv = _supplier_payment(owner, grn, cash)
    assert _payable() == D("30.00")

    void(pv, owner, "keyed twice")

    pv.refresh_from_db()
    assert pv.status == Document.Status.VOIDED
    assert _payable() == D("0.00")


def test_a_stock_shortfall_names_the_medicine(owner, customer):
    """D100: the message used to read 'item 10 lot 12', which named two
    database rows and no medicine."""
    item = Item.objects.create(code="AMOX", name="Amoxicillin", base_unit="pack",
                               is_batch_tracked=True, has_expiry=True,
                               vat_exempt=True, maintained_price=D("100.00"))
    opening = Document.objects.create(doc_type=DocType.OPENING_STOCK,
                                      created_by=owner)
    DocumentLine.objects.create(document=opening, item=item, qty_entered=20,
                                unit_cost_entered=D("50.00"),
                                batch_no_entered="B-1", expiry_entered=FAR,
                                unit_label="pack", factor=1)
    post(opening, owner)
    _credit_sale(owner, customer, item, qty=5)

    with pytest.raises(PostingError) as caught:
        void(opening, owner, "opening was wrong")

    message = str(caught.value)
    assert "AMOX" in message and "Amoxicillin" in message
    assert "B-1" in message
    assert "Warehouse" in message      # not the raw WAREHOUSE token
    assert "have 15, need 20" in message


def test_voiding_a_receiving_names_what_took_the_goods(owner, customer,
                                                       stocked_item):
    """D100: it said 'sold or moved … use a supplier return', which is
    absurd advice when a supplier return is what moved them."""
    grn = Document.objects.get(doc_type=DocType.RECEIVING,
                               status=Document.Status.POSTED)
    sale = _credit_sale(owner, customer, stocked_item, qty=2)

    with pytest.raises(PostingError) as caught:
        void(grn, owner, "wrong supplier")

    assert sale.doc_no in str(caught.value)


def test_the_remittance_itself_still_voids(owner, cash, stocked_item,
                                           withholding_on):
    """A remittance only ever *consumes* the bucket, so reversing it
    refills — it must never be caught by the guard."""
    grn = _receiving(owner, stocked_item)
    _supplier_payment(owner, grn, cash)
    wr = _remit(owner, cash)

    void(wr, owner, "wrong month")

    assert _payable() == D("30.00")


# --- R70: a correction must not silently delete what it cannot rebuild ----

def test_correcting_a_returned_sale_is_refused(client, owner, customer,
                                               stocked_item):
    """The D96 cascade with no way back: voiding the sale reverses its
    customer return, and the replacement sale carries no return, so the
    goods the customer handed back vanish from the warehouse."""
    from django.urls import reverse
    sale = _credit_sale(owner, customer, stocked_item, qty=5)
    cr = _return_against(owner, sale, stocked_item, qty=2)
    stock_before = _warehouse(stocked_item)
    balance_before = _balance(customer)
    client.force_login(owner)

    client.post(reverse("document_correct", args=[sale.pk]),
                {"reason": "wrong quantity"})

    sale.refresh_from_db()
    cr.refresh_from_db()
    assert sale.status == Document.Status.POSTED
    assert cr.status == Document.Status.POSTED
    assert not Document.objects.filter(corrects=sale).exists()
    assert _warehouse(stocked_item) == stock_before
    assert _balance(customer) == balance_before


def test_posting_a_crafted_correction_draft_is_refused(owner, customer, cash,
                                                       stocked_item):
    """The view's check is advisory (D92): the return or receipt can land
    while the draft sits open. Posting is where the refusal binds."""
    sale = _credit_sale(owner, customer, stocked_item, qty=5)
    draft = Document.objects.create(
        doc_type=DocType.SALE, created_by=owner, customer=customer,
        due_date=DUE, sale_kind=Document.SaleKind.CREDIT,
        corrects=sale, correction_reason="wrong quantity",
    )
    DocumentLine.objects.create(
        document=draft, item=stocked_item, batch=Batch.objects.get(item=stocked_item),
        qty_entered=3, unit_price=D("100.00"), unit_label="pack", factor=1,
    )
    # Only now does the receipt arrive — the draft was opened before it.
    receipt = post(_receipt(owner, customer, cash, {sale: D("200.00")}), owner)
    stock_before = _warehouse(stocked_item)
    balance_before = _balance(customer)

    with pytest.raises(PostingError):
        post(draft, owner)

    sale.refresh_from_db()
    draft.refresh_from_db()
    receipt.refresh_from_db()
    assert sale.status == Document.Status.POSTED
    assert receipt.status == Document.Status.POSTED
    assert draft.status == Document.Status.DRAFT
    assert not draft.doc_no                     # never numbered (D8)
    assert _warehouse(stocked_item) == stock_before
    assert _balance(customer) == balance_before


def test_an_ordinary_cash_sale_still_corrects(client, owner, customer, cash,
                                              stocked_item):
    """The guard must not catch a cash sale's own auto payment (D3/D44):
    the correction copies the payment lines and posting rebuilds it."""
    from django.urls import reverse
    sale = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                   customer=customer,
                                   sale_kind=Document.SaleKind.CASH)
    DocumentLine.objects.create(
        document=sale, item=stocked_item, batch=Batch.objects.get(item=stocked_item),
        qty_entered=2, unit_price=D("100.00"), unit_label="pack", factor=1,
    )
    PaymentLine.objects.create(document=sale, account=cash, amount=D("200.00"))
    sale = post(sale, owner)
    client.force_login(owner)

    client.post(reverse("document_correct", args=[sale.pk]),
                {"reason": "wrong quantity"})

    assert Document.objects.filter(corrects=sale,
                                   status=Document.Status.DRAFT).count() == 1
