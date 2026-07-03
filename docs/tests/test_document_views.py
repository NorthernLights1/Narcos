from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Customer, Item
from core.models import AuditLog
from docs.models import Document, DocType, DocumentCharge, DocumentLine
from docs.posting import post
from docs.tests.conftest import make_expense
from money.models import account_balance

pytestmark = pytest.mark.django_db


def login(client, user):
    client.force_login(user)


def payment_formset(account, amount):
    return {
        "payments-TOTAL_FORMS": "1",
        "payments-INITIAL_FORMS": "0",
        "payments-MIN_NUM_FORMS": "0",
        "payments-MAX_NUM_FORMS": "1000",
        "payments-0-account": str(account.pk),
        "payments-0-method": "CASH",
        "payments-0-amount": amount,
    }


def test_expense_draft_create_and_post_from_ui(client, owner, cash, rent):
    login(client, owner)
    response = client.post(
        reverse("document_create", args=[DocType.EXPENSE]),
        {
            "expense_category": str(rent.pk),
            "payee": "Landlord",
            "grand_total": "80.00",
            "notes": "",
        } | payment_formset(cash, "80.00"),
    )
    assert response.status_code == 302
    doc = Document.objects.get(doc_type=DocType.EXPENSE)
    assert doc.status == Document.Status.DRAFT

    response = client.post(reverse("document_post", args=[doc.pk]))
    assert response.status_code == 302
    doc.refresh_from_db()
    assert doc.status == Document.Status.POSTED
    assert doc.doc_no == "EX-000001"
    assert account_balance(cash) == Decimal("-80.00")


def test_posted_reference_edit_is_audited(client, owner, cash, rent):
    login(client, owner)
    doc = post(make_expense(owner, cash, rent), owner)
    response = client.post(
        reverse("document_edit", args=[doc.pk]),
        {
            "fiscal_receipt_no": "FS-123",
            "machine_total": "",
            "withholding_certificate_no": "",
        },
    )
    assert response.status_code == 302
    doc.refresh_from_db()
    assert doc.fiscal_receipt_no == "FS-123"
    assert AuditLog.objects.filter(
        action="DOCUMENT_REFERENCE_UPDATE", entity_id=str(doc.pk)
    ).exists()


def test_employee_cannot_void_from_ui(client, owner, employee, cash, rent):
    doc = post(make_expense(owner, cash, rent), owner)
    login(client, employee)
    response = client.post(reverse("document_void", args=[doc.pk]), {"reason": "x"})
    assert response.status_code == 403
    doc.refresh_from_db()
    assert doc.status == Document.Status.POSTED


def test_posted_proforma_converts_to_draft_sale(client, owner):
    customer = Customer.objects.create(code="C001", name="Selam Pharmacy")
    item = Item.objects.create(
        code="SUP-1", name="Syringe", base_unit="box",
        is_batch_tracked=False, has_expiry=False,
    )
    proforma = Document.objects.create(
        doc_type=DocType.PROFORMA, created_by=owner, customer=customer,
        doc_discount=Decimal("1.00"),
    )
    DocumentLine.objects.create(
        document=proforma, item=item, qty_entered=2, unit_label="box",
        factor=1, unit_price=Decimal("10.00"),
    )
    DocumentCharge.objects.create(
        document=proforma, label="Delivery", amount=Decimal("3.00"), is_taxable=True,
    )
    proforma = post(proforma, owner)

    login(client, owner)
    response = client.post(reverse("document_convert_sale", args=[proforma.pk]))
    assert response.status_code == 302
    sale = Document.objects.get(doc_type=DocType.SALE)
    assert sale.status == Document.Status.DRAFT
    assert sale.customer == customer
    assert sale.doc_discount == Decimal("1.00")
    assert sale.lines.get().item == item
    assert sale.charges.get().label == "Delivery"
