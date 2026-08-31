"""D122: unit conversion is gone. Legacy rows posted on a pack scale must not
be copied into a fresh draft, because the copy would re-post `qty_entered`
alone and register less stock than the original moved."""

from decimal import Decimal as D

import pytest

from catalog.models import Customer, Item, Supplier
from docs.models import Document, DocType, DocumentLine
from docs.posting import (
    PostingError, check_correctable, lines_posted_on_a_pack_scale, post,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def item(db):
    return Item.objects.create(code="PARA", name="Paracetamol", base_unit="pack",
                               is_batch_tracked=False, has_expiry=False,
                               maintained_price=D("20.00"))


def _posted_receiving(owner, item, qty=10, free=0, cost="10.00"):
    supplier = Supplier.objects.create(code=f"S{Supplier.objects.count()+1}", name="Addis")
    doc = Document.objects.create(doc_type=DocType.RECEIVING, created_by=owner,
                                  supplier=supplier)
    DocumentLine.objects.create(document=doc, item=item, qty_entered=qty,
                                free_qty=free, unit_cost_entered=D(cost),
                                unit_label="pack")
    return post(doc, owner)


def _make_legacy(doc, scale=12):
    """Imitate a row posted while `factor` still existed: qty_base carries the
    pack-scaled figure. Written with .update() because posted lines are
    immutable through save() — this is a legacy row, not a new one."""
    line = doc.lines.get()
    DocumentLine.objects.filter(pk=line.pk).update(qty_base=line.qty_entered * scale)
    return doc


def test_an_ordinary_line_is_not_flagged(owner, item):
    grn = _posted_receiving(owner, item, qty=10)
    assert lines_posted_on_a_pack_scale(grn) == []
    check_correctable(grn)          # does not raise


def test_bonus_goods_are_not_mistaken_for_a_pack_scale(owner, item):
    """D21: receiving legitimately registers qty_entered + free_qty."""
    grn = _posted_receiving(owner, item, qty=100, free=10)
    line = grn.lines.get()
    assert line.qty_base == 110 and line.qty_base != line.qty_entered
    assert lines_posted_on_a_pack_scale(grn) == [], "bonus goods false-alarmed"
    check_correctable(grn)          # does not raise


def test_a_legacy_pack_scaled_line_is_found(owner, item):
    grn = _make_legacy(_posted_receiving(owner, item, qty=10), scale=12)
    found = lines_posted_on_a_pack_scale(grn)
    assert [ln.qty_base for ln in found] == [120]


def test_correcting_a_pack_scaled_document_is_refused(owner, item):
    grn = _make_legacy(_posted_receiving(owner, item, qty=10), scale=12)
    with pytest.raises(PostingError) as exc:
        check_correctable(grn)
    message = str(exc.value)
    assert grn.doc_no in message
    assert "PARA" in message
    assert "pack scale" in message


def test_converting_a_pack_scaled_proforma_is_refused(client, owner, item):
    from django.urls import reverse
    customer = Customer.objects.create(code="C1", name="Selam")
    pf = Document.objects.create(doc_type=DocType.PROFORMA, created_by=owner,
                                 customer=customer)
    DocumentLine.objects.create(document=pf, item=item, qty_entered=5,
                                unit_price=D("20.00"), unit_label="carton")
    post(pf, owner)
    _make_legacy(pf, scale=12)

    client.force_login(owner)
    response = client.post(reverse("document_convert_sale", args=[pf.pk]), follow=True)
    assert not Document.objects.filter(doc_type=DocType.SALE).exists(), \
        "a pack-scaled proforma was converted anyway"
    assert "pack scale" in response.content.decode()


def test_a_zero_factor_row_is_refused(owner, item):
    """Codex-HIGH: a historical `factor = 0` line stored qty_base 0 against a
    positive qty_entered. Re-posting it would register stock the original
    never moved, so it must be refused — not skipped for being falsy."""
    grn = _posted_receiving(owner, item, qty=10)
    line = grn.lines.get()
    DocumentLine.objects.filter(pk=line.pk).update(qty_base=0)
    assert [ln.pk for ln in lines_posted_on_a_pack_scale(grn)] == [line.pk]
    with pytest.raises(PostingError):
        check_correctable(grn)


def test_a_settlement_is_not_mistaken_for_a_pack_scale(owner, item):
    """Codex-MEDIUM: settlement writes qty_base = sold+returned+expired, which
    legitimately differs from qty_entered. Refusing to correct it would be a
    false alarm — the marker is scoped to doc types that mean base units."""
    from docs.models import Document as D_
    doc = D_.objects.create(doc_type=DocType.CONSIGNMENT_SETTLEMENT,
                            created_by=owner, doc_no="CS-000001",
                            status=D_.Status.POSTED)
    DocumentLine.objects.filter(
        pk=DocumentLine.objects.create(
            document=D_.objects.create(doc_type=DocType.CONSIGNMENT_SETTLEMENT,
                                       created_by=owner),
            item=item, qty_entered=10, qty_base=7, unit_label="pack").pk
    ).update(document=doc)
    assert lines_posted_on_a_pack_scale(doc) == [], "settlement false-alarmed"


def test_a_correction_carries_bonus_units_it_never_shows(client, owner, item):
    """Codex-HIGH: `free_qty` is engine-live (D21) but off every form since
    D84, so the config-driven correction copy dropped it — voiding 110 units
    and re-posting 100."""
    from django.urls import reverse
    grn = _posted_receiving(owner, item, qty=100, free=10)
    assert grn.lines.get().qty_base == 110

    client.force_login(owner)
    client.post(reverse("document_correct", args=[grn.pk]), {"reason": "typo"})
    draft = Document.objects.filter(corrects=grn).get()
    assert draft.lines.get().free_qty == 10, "bonus units lost in the correction"
