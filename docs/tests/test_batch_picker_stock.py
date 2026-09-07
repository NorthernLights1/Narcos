"""D124: an empty batch is not offered on documents that sell from the shelf.

Posting already refused it (D4) — but only after the whole line was typed,
which is the operator-time complaint this closes. The interesting cases are
the ones where filtering must NOT apply, and the stale draft that must still
save.
"""

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from catalog.models import Customer, Item
from docs.forms import DocumentLineForm
from docs.models import Document, DocType, DocumentLine
from stock.models import Batch, CostLot, StockBalance, Zone

pytestmark = pytest.mark.django_db

EXPIRY = datetime.date(2028, 6, 30)


@pytest.fixture
def drug(db):
    return Item.objects.create(code="AMOX", name="Amoxil", base_unit="pack",
                               is_batch_tracked=True, has_expiry=True,
                               maintained_price=Decimal("10.00"))


def _batch(item, batch_no, warehouse_qty):
    """A batch with a lot, and a warehouse balance only when qty > 0 — so the
    empty case really has no balance row, which is what makes the annotation
    NULL rather than 0."""
    batch = Batch.objects.create(item=item, batch_no=batch_no, expiry_date=EXPIRY)
    lot = CostLot.objects.create(item=item, batch=batch, received_at=timezone.now(),
                                 qty_received=max(warehouse_qty, 1),
                                 unit_cost=Decimal("5.00"))
    if warehouse_qty:
        StockBalance.objects.create(item=item, batch=batch, lot=lot,
                                    zone=Zone.WAREHOUSE, qty=warehouse_qty)
    return batch


def _form(doc_type, instance=None, data=None):
    return DocumentLineForm(
        data, instance=instance, doc_type=doc_type,
        line_fields=["item", "batch", "qty_entered"],
    )


def test_sale_does_not_offer_a_batch_with_no_warehouse_stock(drug):
    full = _batch(drug, "B-FULL", 40)
    empty = _batch(drug, "B-EMPTY", 0)
    offered = set(_form(DocType.SALE).fields["batch"].queryset)
    assert full in offered
    assert empty not in offered


def test_consignment_issue_is_filtered_the_same_way(drug):
    full = _batch(drug, "B-FULL", 40)
    empty = _batch(drug, "B-EMPTY", 0)
    offered = set(_form(DocType.CONSIGNMENT_ISSUE).fields["batch"].queryset)
    assert offered == {full}


@pytest.mark.parametrize("doc_type", [
    DocType.PROFORMA,            # quotes move no stock at all
    DocType.CUSTOMER_RETURN,     # goods come back TO an empty batch
    DocType.ADJUSTMENT,          # writing stock up starts from nothing
    DocType.STOCK_COUNT,         # a count of zero is a real count
    DocType.CONSIGNMENT_SETTLEMENT,  # consumes CONSIGNED, not WAREHOUSE
])
def test_other_document_types_still_see_empty_batches(drug, doc_type):
    empty = _batch(drug, "B-EMPTY", 0)
    assert empty in set(_form(doc_type).fields["batch"].queryset)


def test_a_draft_saved_before_the_batch_ran_dry_still_validates(drug, owner):
    """Without the union this fails with `invalid_choice`, and because
    `_draft_form` gates on every formset validating, the WHOLE document
    stops saving — not just this line."""
    empty = _batch(drug, "B-EMPTY", 0)
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=owner)
    line = DocumentLine.objects.create(document=doc, item=drug, batch=empty,
                                       qty_entered=5, unit_label="pack")

    form = _form(DocType.SALE, instance=line,
                 data={"item": drug.pk, "batch": empty.pk, "qty_entered": 5})
    assert form.is_valid(), form.errors
    assert form.cleaned_data["batch"] == empty


def test_the_rescue_is_scoped_to_that_line_only(drug, owner):
    """One stale line may keep its own empty batch. It must not re-open the
    picker for every other line, or a new line could pick the empty one."""
    stale = _batch(drug, "B-STALE", 0)
    other = _batch(drug, "B-OTHER", 0)
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=owner)
    line = DocumentLine.objects.create(document=doc, item=drug, batch=stale,
                                       qty_entered=5, unit_label="pack")

    offered = set(_form(DocType.SALE, instance=line).fields["batch"].queryset)
    assert stale in offered
    assert other not in offered


def test_a_brand_new_line_is_never_offered_an_empty_batch(drug):
    empty = _batch(drug, "B-EMPTY", 0)
    assert empty not in set(_form(DocType.SALE).fields["batch"].queryset)
