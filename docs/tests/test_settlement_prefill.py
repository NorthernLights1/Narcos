"""Settle button on a posted consignment issue prefines the settlement draft:
one line per item+batch still out, quantities in base units (D6/§7.5)."""

from decimal import Decimal

import pytest
from django.urls import reverse

from docs.models import Document, DocType
from docs.posting import post
from docs.tests.test_p6_consignment import (  # reuse P6 builders
    FAR_EXPIRY, customer, issue, item, receive, supplier,
)

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def logged_in_owner(client, owner):
    client.force_login(owner)
    return owner


def settle_url(issue_doc):
    return (reverse("document_create", args=[DocType.CONSIGNMENT_SETTLEMENT])
            + f"?from={issue_doc.pk}")


def test_settle_button_prefills_outstanding_lines(client, logged_in_owner,
                                                  customer, supplier, item):
    receive(logged_in_owner, supplier, item, qty=10)
    cn = issue(logged_in_owner, customer, item, qty=5)

    response = client.get(settle_url(cn))
    assert response.status_code == 302

    draft = Document.objects.get(doc_type=DocType.CONSIGNMENT_SETTLEMENT,
                                 status=Document.Status.DRAFT)
    assert draft.customer_id == customer.pk
    assert draft.related_document_id == cn.pk
    line = draft.lines.get()
    assert line.item_id == item.pk
    assert line.qty_entered == 5  # what is still out
    assert line.qty_sold == 0 and line.qty_returned == 0


def test_prefill_subtracts_prior_settlements(client, logged_in_owner,
                                             customer, supplier, item):
    receive(logged_in_owner, supplier, item, qty=10)
    cn = issue(logged_in_owner, customer, item, qty=5)
    first = Document.objects.create(
        doc_type=DocType.CONSIGNMENT_SETTLEMENT, created_by=logged_in_owner,
        customer=customer, related_document=cn,
        sale_kind=Document.SaleKind.CASH,
    )
    from docs.models import DocumentLine
    from money.models import PaymentLine
    from catalog.models import Account
    line = DocumentLine.objects.create(
        document=first, item=item, batch=cn.lines.get().batch,
        unit_label="kit", factor=1, qty_entered=2, qty_sold=2,
    )
    account = Account.objects.create(name="Cash", type=Account.Type.CASH)
    PaymentLine.objects.create(document=first, account=account, amount=D("230.00"))
    post(first, logged_in_owner)

    response = client.get(settle_url(cn))
    assert response.status_code == 302
    draft = Document.objects.filter(
        doc_type=DocType.CONSIGNMENT_SETTLEMENT, status=Document.Status.DRAFT,
    ).get()
    assert draft.lines.get().qty_entered == 3  # 5 issued − 2 already sold


def test_fully_settled_issue_redirects_back_with_message(client, logged_in_owner,
                                                         customer, supplier, item):
    receive(logged_in_owner, supplier, item, qty=10)
    cn = issue(logged_in_owner, customer, item, qty=2)
    full = Document.objects.create(
        doc_type=DocType.CONSIGNMENT_SETTLEMENT, created_by=logged_in_owner,
        customer=customer, related_document=cn,
        sale_kind=Document.SaleKind.CASH,
    )
    from docs.models import DocumentLine
    from money.models import PaymentLine
    from catalog.models import Account
    DocumentLine.objects.create(
        document=full, item=item, batch=cn.lines.get().batch,
        unit_label="kit", factor=1, qty_entered=2, qty_sold=2,
    )
    account = Account.objects.create(name="Cash", type=Account.Type.CASH)
    PaymentLine.objects.create(document=full, account=account, amount=D("230.00"))
    post(full, logged_in_owner)

    response = client.get(settle_url(cn))
    assert response.status_code == 302
    assert response.url == reverse("document_detail", args=[cn.pk])
    assert not Document.objects.filter(
        doc_type=DocType.CONSIGNMENT_SETTLEMENT, status=Document.Status.DRAFT,
    ).exists()


def test_settlement_inherits_withholding_from_issue(client, logged_in_owner,
                                                    customer, supplier, item):
    """D70: the flag is decided on the issue; the settlement inherits it even
    when created without it (blank-form path)."""
    import datetime

    from core.models import CompanySettings
    from docs.models import DocumentLine
    from stock.models import Batch

    settings = CompanySettings.load()
    settings.withholding_on_sales = True
    settings.save()

    receive(logged_in_owner, supplier, item, qty=10)
    cn = Document.objects.create(
        doc_type=DocType.CONSIGNMENT_ISSUE, created_by=logged_in_owner,
        customer=customer, customer_will_withhold=True,
    )
    DocumentLine.objects.create(document=cn, item=item, batch=Batch.objects.get(),
                                qty_entered=5, unit_price=D("100.00"),
                                unit_label="kit", factor=1)
    post(cn, logged_in_owner)

    cs = Document.objects.create(
        doc_type=DocType.CONSIGNMENT_SETTLEMENT, created_by=logged_in_owner,
        customer=customer, related_document=cn,
        sale_kind=Document.SaleKind.CREDIT,
        due_date=datetime.date(2030, 1, 1),
    )
    DocumentLine.objects.create(document=cs, item=item, batch=Batch.objects.get(),
                                unit_label="kit", factor=1,
                                qty_entered=2, qty_sold=2)
    post(cs, logged_in_owner)

    cs.refresh_from_db()
    assert cs.customer_will_withhold is True  # inherited, not entered
    # sold 2 × 100 = 200 net + 15% VAT = 230; withholding 3% of the 200 net
    assert cs.withholding_expected == D("6.00")


def test_settlement_expected_totals_price_sold_only(client, logged_in_owner,
                                                    customer, supplier, item):
    """The draft's expected money = sold × issue price (+ issue-rate tax);
    returned and expired quantities earn nothing."""
    from docs.preview import draft_expected_totals

    receive(logged_in_owner, supplier, item, qty=10)
    cn = issue(logged_in_owner, customer, item, qty=5, price="100.00")

    client.get(settle_url(cn))  # prefill draft: 5 still out
    draft = Document.objects.get(doc_type=DocType.CONSIGNMENT_SETTLEMENT,
                                 status=Document.Status.DRAFT)
    line = draft.lines.get()
    line.qty_sold = 2
    line.qty_returned = 2
    line.qty_expired_unfit = 1
    line.save()

    expected = draft_expected_totals(draft)
    assert expected["subtotal"] == D("200.00")   # only the 2 sold
    assert expected["tax"] == D("30.00")         # issue's 15% snapshot
    assert expected["grand"] == D("230.00")
