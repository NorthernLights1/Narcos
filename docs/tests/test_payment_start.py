"""D74: Record payment / Pay supplier buttons create a prefilled RC/PV draft
(?from=<invoice>), and allocation target options carry the party so picking an
invoice on a blank payment form can fill the customer/supplier box."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Customer, Item, Supplier
from core.models import CompanySettings
from docs.models import Document, DocType, DocumentLine
from docs.posting import post
from money.models import PaymentAllocation, PaymentLine
from stock.models import Batch

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


def credit_sale(actor, customer, item, qty=100, price="15.00", withhold=False):
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=actor,
                                  customer=customer, sale_kind="CREDIT",
                                  due_date=datetime.date(2026, 8, 1),
                                  customer_will_withhold=withhold)
    DocumentLine.objects.create(document=doc, item=item, batch=Batch.objects.get(),
                                qty_entered=qty, unit_price=D(price),
                                unit_label="kit", factor=1)
    return post(doc, actor)


def start_payment(client, doc_type, target):
    return client.get(reverse("document_create", args=[doc_type]),
                      {"from": target.pk})


def test_record_payment_creates_prefilled_rc_draft(client, owner, customer,
                                                   supplier, item):
    receive(owner, supplier, item)
    sale = credit_sale(owner, customer, item)  # 1500 open
    client.force_login(owner)
    response = start_payment(client, DocType.CUSTOMER_PAYMENT, sale)
    rc = Document.objects.get(doc_type=DocType.CUSTOMER_PAYMENT)
    assert response.status_code == 302
    assert response.url == reverse("document_edit", args=[rc.pk])
    assert rc.status == Document.Status.DRAFT
    assert rc.customer_id == customer.pk
    assert rc.withheld_amount == 0
    allocation = PaymentAllocation.objects.get(payment=rc)
    assert allocation.target_id == sale.pk
    assert allocation.amount == D("1500.00")


def test_record_payment_prefills_expected_withholding(client, owner, customer,
                                                      supplier, item):
    settings = CompanySettings.load()
    settings.withholding_on_sales = True
    settings.save()
    receive(owner, supplier, item)
    sale = credit_sale(owner, customer, item, withhold=True)
    assert sale.withholding_expected > 0
    client.force_login(owner)
    start_payment(client, DocType.CUSTOMER_PAYMENT, sale)
    rc = Document.objects.get(doc_type=DocType.CUSTOMER_PAYMENT)
    assert rc.withheld_amount == sale.withholding_expected


def test_record_payment_only_allocates_the_remaining_balance(
        client, owner, customer, supplier, item, cash):
    receive(owner, supplier, item)
    sale = credit_sale(owner, customer, item)  # 1500
    partial = Document.objects.create(doc_type=DocType.CUSTOMER_PAYMENT,
                                      created_by=owner, customer=customer)
    PaymentLine.objects.create(document=partial, account=cash, amount=D("600.00"))
    PaymentAllocation.objects.create(payment=partial, target=sale, amount=D("600.00"))
    post(partial, owner)
    client.force_login(owner)
    start_payment(client, DocType.CUSTOMER_PAYMENT, sale)
    draft = Document.objects.get(doc_type=DocType.CUSTOMER_PAYMENT,
                                 status=Document.Status.DRAFT)
    assert PaymentAllocation.objects.get(payment=draft).amount == D("900.00")


def test_settled_invoice_redirects_back_without_a_draft(client, owner, customer,
                                                        supplier, item, cash):
    receive(owner, supplier, item)
    sale = credit_sale(owner, customer, item)
    rc = Document.objects.create(doc_type=DocType.CUSTOMER_PAYMENT,
                                 created_by=owner, customer=customer)
    PaymentLine.objects.create(document=rc, account=cash, amount=D("1500.00"))
    PaymentAllocation.objects.create(payment=rc, target=sale, amount=D("1500.00"))
    post(rc, owner)
    client.force_login(owner)
    response = start_payment(client, DocType.CUSTOMER_PAYMENT, sale)
    assert response.status_code == 302
    assert response.url == reverse("document_detail", args=[sale.pk])
    assert not Document.objects.filter(doc_type=DocType.CUSTOMER_PAYMENT,
                                       status=Document.Status.DRAFT).exists()


def test_pay_supplier_creates_prefilled_pv_draft(client, owner, supplier, item):
    grn = receive(owner, supplier, item)  # 1000 AP
    client.force_login(owner)
    response = start_payment(client, DocType.SUPPLIER_PAYMENT, grn)
    pv = Document.objects.get(doc_type=DocType.SUPPLIER_PAYMENT)
    assert response.status_code == 302
    assert pv.supplier_id == supplier.pk
    assert PaymentAllocation.objects.get(payment=pv).amount == D("1000.00")


def test_detail_page_offers_the_button_only_while_open(client, owner, customer,
                                                       supplier, item, cash):
    receive(owner, supplier, item)
    sale = credit_sale(owner, customer, item)
    grn = Document.objects.get(doc_type=DocType.RECEIVING)
    client.force_login(owner)
    content = client.get(reverse("document_detail", args=[sale.pk])).content.decode()
    assert "Record payment" in content
    content = client.get(reverse("document_detail", args=[grn.pk])).content.decode()
    assert "Pay supplier" in content

    rc = Document.objects.create(doc_type=DocType.CUSTOMER_PAYMENT,
                                 created_by=owner, customer=customer)
    PaymentLine.objects.create(document=rc, account=cash, amount=D("1500.00"))
    PaymentAllocation.objects.create(payment=rc, target=sale, amount=D("1500.00"))
    post(rc, owner)
    content = client.get(reverse("document_detail", args=[sale.pk])).content.decode()
    assert "Record payment" not in content


def test_target_options_carry_the_party_for_client_prefill(client, owner,
                                                           customer, supplier,
                                                           item):
    receive(owner, supplier, item)
    credit_sale(owner, customer, item)
    client.force_login(owner)
    content = client.get(
        reverse("document_create", args=[DocType.CUSTOMER_PAYMENT])
    ).content.decode()
    assert f'data-customer="{customer.pk}"' in content
    content = client.get(
        reverse("document_create", args=[DocType.SUPPLIER_PAYMENT])
    ).content.decode()
    assert f'data-supplier="{supplier.pk}"' in content
