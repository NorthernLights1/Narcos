"""P5: payments + withholding. I12 (withholding never touches revenue/COGS/
profit — D53), I13 (allocations never exceed open balance — D44)."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Customer, Item, Supplier
from core.models import CompanySettings
from docs.handlers_payments import open_balance, withholding_balance
from docs.models import Document, DocType, DocumentLine
from docs.posting import PostingError, post, void
from money.models import PaymentAllocation, PaymentLine, account_balance

pytestmark = pytest.mark.django_db

D = Decimal
FAR_EXPIRY = datetime.date(2030, 1, 1)


@pytest.fixture
def customer(db):
    return Customer.objects.create(code="C001", name="Mekelle Hospital PLC",
                                   is_withholding_agent=True)


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(code="S001", name="Addis Pharma")


@pytest.fixture
def drug(db):
    return Item.objects.create(code="AMOX", name="Amoxicillin", base_unit="pack",
                               is_batch_tracked=True, has_expiry=True, vat_exempt=True)


@pytest.fixture
def wht_settings(db):
    settings = CompanySettings.load()
    settings.withholding_on_sales = True
    settings.withholding_on_purchases = True
    settings.save()
    return settings


def receive(actor, supplier, drug, qty=100, cost="10.00"):
    doc = Document.objects.create(doc_type=DocType.RECEIVING, created_by=actor,
                                  supplier=supplier)
    DocumentLine.objects.create(document=doc, item=drug, qty_entered=qty,
                                unit_cost_entered=D(cost), batch_no_entered="B-1",
                                expiry_entered=FAR_EXPIRY, unit_label="pack", factor=1)
    return post(doc, actor)


def credit_sale(actor, customer, drug, qty=100, price="15.00", withhold=False):
    from stock.models import Batch

    doc = Document.objects.create(doc_type=DocType.SALE, created_by=actor,
                                  customer=customer, sale_kind="CREDIT",
                                  due_date=datetime.date(2026, 8, 1),
                                  customer_will_withhold=withhold)
    DocumentLine.objects.create(document=doc, item=drug, batch=Batch.objects.get(),
                                qty_entered=qty, unit_price=D(price),
                                unit_label="pack", factor=1)
    return post(doc, actor)


def rc_draft(actor, customer, targets_amounts, cash_account=None, cash="0.00",
             withheld="0.00", certificate="") -> Document:
    doc = Document.objects.create(doc_type=DocType.CUSTOMER_PAYMENT,
                                  created_by=actor, customer=customer,
                                  withheld_amount=D(withheld),
                                  withholding_certificate_no=certificate)
    if D(cash) > 0:
        PaymentLine.objects.create(document=doc, account=cash_account, amount=D(cash))
    for target, amount in targets_amounts:
        PaymentAllocation.objects.create(payment=doc, target=target, amount=D(amount))
    return doc


# --- Basic settlement (D3/D44) ---


def test_full_payment_settles_invoice(owner, customer, supplier, drug, cash):
    receive(owner, supplier, drug)
    sale = credit_sale(owner, customer, drug)  # 1500 AR
    rc = rc_draft(owner, customer, [(sale, "1500.00")], cash, cash="1500.00")
    rc = post(rc, owner)
    assert rc.doc_no == "RC-000001"
    assert account_balance(cash) == D("1500.00")
    assert open_balance(sale) == D("0.00")
    from docs.checks import ar_balance
    assert ar_balance(customer.pk) == D("0.00")


def test_i13_partial_payments_and_cap(owner, customer, supplier, drug, cash):
    receive(owner, supplier, drug)
    sale = credit_sale(owner, customer, drug)  # 1500
    post(rc_draft(owner, customer, [(sale, "600.00")], cash, cash="600.00"), owner)
    assert open_balance(sale) == D("900.00")
    # allocation exceeding the open balance is rejected (I13)
    over = rc_draft(owner, customer, [(sale, "901.00")], cash, cash="901.00")
    with pytest.raises(PostingError):
        post(over, owner)
    # exactly the remainder is fine
    post(rc_draft(owner, customer, [(sale, "900.00")], cash, cash="900.00"), owner)
    assert open_balance(sale) == D("0.00")


def test_allocations_must_equal_payment_total(owner, customer, supplier, drug, cash):
    receive(owner, supplier, drug)
    sale = credit_sale(owner, customer, drug)
    bad = rc_draft(owner, customer, [(sale, "1000.00")], cash, cash="900.00")
    with pytest.raises(PostingError):  # D44: no advances/overpay
        post(bad, owner)


def test_split_cash_bank_payment(owner, customer, supplier, drug, cash, bank):
    receive(owner, supplier, drug)
    sale = credit_sale(owner, customer, drug)
    rc = rc_draft(owner, customer, [(sale, "1500.00")])
    PaymentLine.objects.create(document=rc, account=cash, amount=D("500.00"))
    PaymentLine.objects.create(document=rc, account=bank, amount=D("1000.00"))
    post(rc, owner)
    assert account_balance(cash) == D("500.00")
    assert account_balance(bank) == D("1000.00")


def test_payment_to_wrong_customer_invoice_rejected(owner, customer, supplier, drug, cash):
    receive(owner, supplier, drug)
    sale = credit_sale(owner, customer, drug)
    other = Customer.objects.create(code="C002", name="Other Pharmacy")
    bad = rc_draft(owner, other, [(sale, "100.00")], cash, cash="100.00")
    with pytest.raises(PostingError):
        post(bad, owner)


def test_voided_payment_reopens_invoice(owner, customer, supplier, drug, cash):
    receive(owner, supplier, drug)
    sale = credit_sale(owner, customer, drug)
    rc = post(rc_draft(owner, customer, [(sale, "1500.00")], cash, cash="1500.00"), owner)
    assert open_balance(sale) == D("0.00")
    void(rc, owner, "bounced cheque")
    assert open_balance(sale) == D("1500.00")  # allocation no longer counts
    assert account_balance(cash) == D("0.00")


# --- I12: withholding never touches revenue/COGS/profit (D53) ---


def test_i12_withholding_identical_revenue_and_profit(owner, supplier, drug,
                                                      cash, wht_settings):
    receive(owner, supplier, drug, qty=200)
    plain = Customer.objects.create(code="C-P", name="Plain customer")
    agent = Customer.objects.create(code="C-A", name="PLC customer",
                                    is_withholding_agent=True)
    sale_plain = credit_sale(owner, plain, drug, qty=100)   # 1500
    sale_wht = credit_sale(owner, agent, drug, qty=100, withhold=True)

    # Identical revenue, tax and COGS on the documents themselves
    assert sale_plain.grand_total == sale_wht.grand_total == D("1500.00")
    assert sale_plain.lines.get().cogs_total == sale_wht.lines.get().cogs_total

    # Settle both: plain pays 1500 cash; agent pays 1455 cash + 45 withheld (3%)
    post(rc_draft(owner, plain, [(sale_plain, "1500.00")], cash, cash="1500.00"), owner)
    post(rc_draft(owner, agent, [(sale_wht, "1500.00")], cash, cash="1455.00",
                  withheld="45.00", certificate="WHT-001"), owner)

    # Both invoices fully settled (I12)
    assert open_balance(sale_plain) == D("0.00")
    assert open_balance(sale_wht) == D("0.00")
    # Only the bucket placement differs: 45 sits in withholding receivable
    assert withholding_balance("RECEIVABLE") == D("45.00")
    assert account_balance(cash) == D("2955.00")  # 1500 + 1455


def test_withholding_needs_setting_enabled(owner, customer, supplier, drug, cash):
    receive(owner, supplier, drug)
    sale = credit_sale(owner, customer, drug)
    rc = rc_draft(owner, customer, [(sale, "1500.00")], cash, cash="1455.00",
                  withheld="45.00")
    with pytest.raises(PostingError):  # withholding_on_sales is off by default
        post(rc, owner)


# --- Supplier side (D52) + remittance ---


def test_supplier_payment_with_withholding_and_remittance(owner, supplier, drug,
                                                          cash, wht_settings):
    grn = receive(owner, supplier, drug)  # AP 1000
    pv = Document.objects.create(doc_type=DocType.SUPPLIER_PAYMENT,
                                 created_by=owner, supplier=supplier,
                                 withheld_amount=D("30.00"))
    PaymentLine.objects.create(document=pv, account=cash, amount=D("970.00"))
    PaymentAllocation.objects.create(payment=pv, target=grn, amount=D("1000.00"))
    pv = post(pv, owner)
    assert pv.doc_no == "PV-000001"
    assert open_balance(grn) == D("0.00")  # settled in full (cash + withheld)
    assert account_balance(cash) == D("-970.00")
    assert withholding_balance("PAYABLE") == D("30.00")

    # Remit the withheld 30 to the tax office (monthly, D52)
    wr = Document.objects.create(doc_type=DocType.WHT_REMITTANCE, created_by=owner)
    PaymentLine.objects.create(document=wr, account=cash, amount=D("30.00"))
    wr = post(wr, owner)
    assert wr.doc_no == "WR-000001"
    assert withholding_balance("PAYABLE") == D("0.00")
    assert account_balance(cash) == D("-1000.00")


def test_supplier_withholding_certificate_print(client, owner, supplier, drug,
                                                cash, wht_settings):
    grn = receive(owner, supplier, drug)
    pv = Document.objects.create(
        doc_type=DocType.SUPPLIER_PAYMENT,
        created_by=owner,
        supplier=supplier,
        withheld_amount=D("30.00"),
        withholding_certificate_no="PV-WHT-1",
    )
    PaymentLine.objects.create(document=pv, account=cash, amount=D("970.00"))
    PaymentAllocation.objects.create(payment=pv, target=grn, amount=D("1000.00"))
    pv = post(pv, owner)

    client.force_login(owner)
    response = client.get(reverse("withholding_certificate_print", args=[pv.pk]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Withholding certificate" in content
    assert "PV-WHT-1" in content
    assert "30.00" in content


def test_remittance_cannot_exceed_payable(owner, cash, wht_settings):
    wr = Document.objects.create(doc_type=DocType.WHT_REMITTANCE, created_by=owner)
    PaymentLine.objects.create(document=wr, account=cash, amount=D("10.00"))
    with pytest.raises(PostingError):  # nothing withheld yet
        post(wr, owner)


def test_allocations_frozen_after_posting(owner, customer, supplier, drug, cash):
    receive(owner, supplier, drug)
    sale = credit_sale(owner, customer, drug)
    rc = post(rc_draft(owner, customer, [(sale, "1500.00")], cash, cash="1500.00"), owner)
    allocation = rc.allocations_made.get()
    allocation.amount = D("1.00")
    with pytest.raises(ValueError):
        allocation.save()
