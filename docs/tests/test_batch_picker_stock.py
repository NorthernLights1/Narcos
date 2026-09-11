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
from core.models import CompanySettings
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


# --- F1: an expired batch is not offered where stock is sold from the shelf ---
#
# Same shape as D124 above and the same reason: posting already refuses it
# (D46, block with no override, docs/handlers_sales.py) but only after the
# whole line has been typed. The difference is that this one is live — item
# ITM-0109 batch B-03225 expired 2026-08-08 and still holds 50 units in the
# warehouse zone on the client's machine.

def _dated_batch(item, batch_no, expiry, warehouse_qty=40):
    batch = _batch(item, batch_no, warehouse_qty)
    Batch.objects.filter(pk=batch.pk).update(expiry_date=expiry)
    batch.refresh_from_db()
    return batch


def test_sale_does_not_offer_an_expired_batch(drug):
    today = timezone.localdate()
    good = _dated_batch(drug, "B-GOOD", today + datetime.timedelta(days=30))
    expired = _dated_batch(drug, "B-EXPIRED", today - datetime.timedelta(days=1))
    offered = set(_form(DocType.SALE).fields["batch"].queryset)
    assert good in offered
    assert expired not in offered


def test_the_expiry_day_itself_is_still_sellable(drug):
    """D46 is explicit: expired means *past* its date, so a batch expiring
    today is still good today. Getting this off by one silently destroys a
    day of shelf life on every batch in the catalogue."""
    today = _dated_batch(drug, "B-TODAY", timezone.localdate())
    assert today in set(_form(DocType.SALE).fields["batch"].queryset)


def test_a_batch_with_no_expiry_is_still_offered(drug):
    """`expiry_date` is null for an item that has no expiry (D22). A null must
    never read as expired, or those items become unsellable."""
    forever = _dated_batch(drug, "B-NONE", None)
    assert forever in set(_form(DocType.SALE).fields["batch"].queryset)


def test_consignment_issue_is_filtered_by_expiry_too(drug):
    today = timezone.localdate()
    expired = _dated_batch(drug, "B-EXPIRED", today - datetime.timedelta(days=1))
    assert expired not in set(
        _form(DocType.CONSIGNMENT_ISSUE).fields["batch"].queryset)


@pytest.mark.parametrize("doc_type", [
    DocType.ADJUSTMENT,          # writing expired stock off REQUIRES picking it
    DocType.STOCK_COUNT,         # counting the shelf includes what is expired
    DocType.CUSTOMER_RETURN,     # expired goods come back
    DocType.PROFORMA,            # quotes move no stock
])
def test_the_types_that_must_still_reach_expired_stock_can(drug, doc_type):
    """The point of the exclusion is to stop an expired batch being *sold*.
    Disposing of it, counting it and taking it back are how it leaves the
    building, and every one of those needs it in the picker."""
    today = timezone.localdate()
    expired = _dated_batch(drug, "B-EXPIRED", today - datetime.timedelta(days=1))
    assert expired in set(_form(doc_type).fields["batch"].queryset)


def test_a_draft_naming_a_batch_that_has_since_expired_still_validates(drug, owner):
    """The D124 rescue, on the expiry axis. Without it the whole document
    stops saving and re-opening it submits blank."""
    today = timezone.localdate()
    expired = _dated_batch(drug, "B-EXPIRED", today - datetime.timedelta(days=1))
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=owner)
    line = DocumentLine.objects.create(document=doc, item=drug, batch=expired,
                                       qty_entered=5, unit_label="pack")

    form = _form(DocType.SALE, instance=line,
                 data={"item": drug.pk, "batch": expired.pk, "qty_entered": 5})
    assert form.is_valid(), form.errors
    assert form.cleaned_data["batch"] == expired


def test_the_expiry_rescue_is_scoped_to_that_line_only(drug, owner):
    today = timezone.localdate()
    stale = _dated_batch(drug, "B-STALE", today - datetime.timedelta(days=1))
    other = _dated_batch(drug, "B-OTHER", today - datetime.timedelta(days=1))
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=owner)
    line = DocumentLine.objects.create(document=doc, item=drug, batch=stale,
                                       qty_entered=5, unit_label="pack")

    offered = set(_form(DocType.SALE, instance=line).fields["batch"].queryset)
    assert stale in offered
    assert other not in offered


def test_a_near_expiry_batch_says_so_in_the_picker(drug):
    """D59: near-expiry stock is still sellable and posting does not refuse it,
    so the picker is the only place the operator can be told. Without this the
    oldest stock is sold by accident rather than on purpose."""
    today = timezone.localdate()
    _dated_batch(drug, "B-SOON", today + datetime.timedelta(days=30))
    _dated_batch(drug, "B-LATER", today + datetime.timedelta(days=900))

    field = _form(DocType.SALE).fields["batch"]
    labels = {b.batch_no: field.label_from_instance(b) for b in field.queryset}
    assert "near expiry" in labels["B-SOON"]
    assert "near expiry" not in labels["B-LATER"]


def test_the_near_expiry_marker_respects_the_configured_window(drug):
    """The window is a setting (D59), so the marker must read it rather than
    hard-code six months."""
    settings = CompanySettings.load()
    settings.near_expiry_months = 1
    settings.save(update_fields=["near_expiry_months"])

    today = timezone.localdate()
    _dated_batch(drug, "B-INSIDE", today + datetime.timedelta(days=10))
    _dated_batch(drug, "B-OUTSIDE", today + datetime.timedelta(days=120))

    field = _form(DocType.SALE).fields["batch"]
    labels = {b.batch_no: field.label_from_instance(b) for b in field.queryset}
    assert "near expiry" in labels["B-INSIDE"]
    assert "near expiry" not in labels["B-OUTSIDE"]
