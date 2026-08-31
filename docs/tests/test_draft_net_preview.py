"""R54: a saved draft's per-line Net column read 0.00 because `line_net`
is frozen at posting (※) and defaults to zero. Drafts now show a computed
preview — display only, clearly labelled; posting stays authoritative
(tax allocation and D80 re-derivation can still move the figure)."""

from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Customer, Item
from docs.models import Document, DocType, DocumentLine

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def draft_sale(owner):
    item = Item.objects.create(code="AMOX", name="Amoxil", base_unit="pack",
                               maintained_price=D("15.00"))
    customer = Customer.objects.create(code="C1", name="Selam Pharmacy")
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                  customer=customer)
    DocumentLine.objects.create(document=doc, item=item, qty_entered=3,
                                unit_price=D("15.00"), line_discount=D("5.00"),
                                unit_label="pack")
    return doc


def test_preview_matches_the_posting_formula(draft_sale):
    line = draft_sale.lines.get()
    assert line.line_net == 0            # the frozen figure stays untouched
    assert line.net_preview == D("40.00")  # 3 × 15.00 − 5.00


def test_draft_detail_shows_the_preview_labelled_as_one(client, owner, draft_sale):
    client.force_login(owner)
    content = client.get(
        reverse("document_detail", args=[draft_sale.pk])).content.decode()
    assert "Net (preview)" in content
    assert "40.00" in content
