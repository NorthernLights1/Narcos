"""D125: a retired item stops being offered for new documents.

`is_active` existed, was editable in Master and audited — and no picker read
it, so deactivating an item changed nothing. This also makes "supersede" a
real option later: retiring a duplicate finally stops staff picking it.
"""

from decimal import Decimal

import pytest

from catalog.models import Item
from docs.forms import DocumentLineForm
from docs.models import Document, DocType, DocumentLine

pytestmark = pytest.mark.django_db


def _item(code, active=True):
    return Item.objects.create(code=code, name=f"Item {code}", base_unit="pack",
                               is_batch_tracked=False, has_expiry=False,
                               maintained_price=Decimal("10.00"), is_active=active)


def _form(instance=None, data=None):
    return DocumentLineForm(data, instance=instance, doc_type=DocType.SALE,
                            line_fields=["item", "qty_entered"])


def test_a_retired_item_is_not_offered():
    live, retired = _item("LIVE"), _item("RETIRED", active=False)
    offered = set(_form().fields["item"].queryset)
    assert live in offered
    assert retired not in offered


def test_a_draft_already_naming_a_retired_item_still_saves(owner):
    retired = _item("RETIRED", active=False)
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=owner)
    line = DocumentLine.objects.create(document=doc, item=retired,
                                       qty_entered=3, unit_label="pack")

    form = _form(instance=line, data={"item": retired.pk, "qty_entered": 3})
    assert form.is_valid(), form.errors


def test_the_rescue_does_not_reopen_the_picker_for_other_retired_items(owner):
    retired = _item("RETIRED", active=False)
    another = _item("ALSO-RETIRED", active=False)
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=owner)
    line = DocumentLine.objects.create(document=doc, item=retired,
                                       qty_entered=3, unit_label="pack")

    offered = set(_form(instance=line).fields["item"].queryset)
    assert retired in offered
    assert another not in offered
