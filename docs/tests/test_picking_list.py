"""R53: printing a draft is a *picking list* for the storeroom (the owner's
answer, 2026-08-03) — not a watermarked invoice. Its own layout: item,
batch, shelf/bin, quantity, a tick column — and no money anywhere, because
a draft has no number (D8) and is not a record of a transaction (D18)."""

from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Customer, Item, Supplier
from docs.models import Document, DocType, DocumentLine

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def draft_sale(owner):
    item = Item.objects.create(code="AMOX", name="Amoxil",
                               generic_name="Amoxicillin", base_unit="pack",
                               strength="500mg", pack_description="strip of 10",
                               shelf_bin="A3", maintained_price=D("15.00"))
    customer = Customer.objects.create(code="C1", name="Selam Pharmacy")
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                  customer=customer)
    DocumentLine.objects.create(document=doc, item=item, qty_entered=4,
                                unit_price=D("15.00"), unit_label="pack",
                                factor=1)
    return doc


def test_draft_prints_as_picking_list(client, owner, draft_sale):
    client.force_login(owner)
    content = client.get(
        reverse("document_picking_list", args=[draft_sale.pk])).content.decode()
    assert "Picking list" in content
    assert "Amoxicillin" in content       # generic-first naming (R48)
    assert "A3" in content                # shelf/bin — the storeroom locator
    assert "Selam Pharmacy" in content
    assert "Draft" in content             # no number exists yet (D8)


def test_picking_list_carries_the_full_description_in_a_grid(client, owner, draft_sale):
    """R58: strength and pack description identify the medicine on the
    shelf; the table gets full grid borders."""
    client.force_login(owner)
    content = client.get(
        reverse("document_picking_list", args=[draft_sale.pk])).content.decode()
    assert "500mg" in content
    assert "strip of 10" in content
    assert "th, td { border: 1px solid" in content


def test_picking_list_shows_no_prices(client, owner, draft_sale):
    client.force_login(owner)
    content = client.get(
        reverse("document_picking_list", args=[draft_sale.pk])).content.decode()
    assert "15.00" not in content
    assert "Total" not in content


def test_receivings_have_no_picking_list(client, owner):
    supplier = Supplier.objects.create(code="S1", name="Addis Pharma")
    doc = Document.objects.create(doc_type=DocType.RECEIVING,
                                  created_by=owner, supplier=supplier)
    client.force_login(owner)
    response = client.get(reverse("document_picking_list", args=[doc.pk]))
    assert response.status_code == 404


def test_draft_detail_offers_the_picking_list(client, owner, draft_sale):
    client.force_login(owner)
    content = client.get(
        reverse("document_detail", args=[draft_sale.pk])).content.decode()
    assert reverse("document_picking_list", args=[draft_sale.pk]) in content
