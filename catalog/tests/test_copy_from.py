"""D142: copy an item you already stock, then edit what differs.

The catalogue's real defect is boxes left empty and sizes typed into the name
(06-client-data.md §3), because describing the eleventh strength of a drug
already stocked means retyping nine boxes. Copying fills all of them.

D139 offered the same idea while deliberately withholding `name` and
`strength`. The owner overruled it: prefill everything, edit what differs.
These tests pin that the copy is complete and that the two things the copy
must never carry — the code and a retired item — stay out.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Item
from catalog.presets import COPIED_FIELDS, item_copy_context
from core.models import User

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def owner():
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


@pytest.fixture
def staff():
    return User.objects.create_user("clerk", password="pw", role=User.Role.EMPLOYEE)


@pytest.fixture
def source():
    return Item.objects.create(
        code="ITM-0001", name="Amoxil", generic_name="amoxicillin",
        strength="500 mg", dosage_form="capsule", pack_description="box of 100",
        base_unit="capsule", category=Item.Category.DRUG, vat_exempt=True,
        is_batch_tracked=True, has_expiry=True, maintained_price=D("12.50"),
        reorder_level=20, shelf_bin="A3",
    )


def _data(item):
    return item_copy_context(True)["copy_data"][str(item.pk)]


def test_the_copy_carries_the_brand_and_the_strength(source):
    """The opposite of D139, by the owner's decision: both are copied, and
    the operator edits the one that differs."""
    values = _data(source)
    assert values["name"] == "Amoxil"
    assert values["strength"] == "500 mg"


def test_the_copy_carries_every_box_the_form_shows(source):
    values = _data(source)
    assert values["generic_name"] == "amoxicillin"
    assert values["dosage_form"] == "capsule"
    assert values["pack_description"] == "box of 100"
    assert values["base_unit"] == "capsule"
    assert values["category"] == "DRUG"
    assert values["maintained_price"] == "12.50"
    assert values["reorder_level"] == "20"
    assert values["shelf_bin"] == "A3"


def test_the_flags_stay_boolean_so_the_checkboxes_can_take_them(source):
    values = _data(source)
    assert values["vat_exempt"] is True
    assert values["is_batch_tracked"] is True
    assert values["has_expiry"] is True


def test_an_empty_box_copies_as_empty_not_as_none(source):
    """`None` in the JSON would put the text "None" in a number box."""
    source.auto_margin_pct = None
    source.save()
    assert _data(source)["auto_margin_pct"] == ""


def test_the_code_is_never_copied(source):
    """D67 assigns it at save, like a document number."""
    assert "code" not in COPIED_FIELDS
    assert "code" not in _data(source)


def test_a_retired_item_is_not_offered_as_a_source(source):
    """D125: copying from one would spread a description already withdrawn."""
    Item.objects.create(code="ITM-0002", name="Old brand", is_active=False,
                        maintained_price=D("1.00"))
    context = item_copy_context(True)
    assert [item.code for item in context["copy_items"]] == ["ITM-0001"]


def test_nothing_is_built_when_the_picker_is_not_offered():
    assert item_copy_context(False) == {"copy_items": [], "copy_data": {}}


# --- where it appears -----------------------------------------------------

def test_the_item_create_page_offers_it(client, owner, source):
    client.force_login(owner)
    content = client.get(reverse("master_create", args=["items"])).content.decode()
    assert "data-copy-source" in content
    assert "Copy from" in content
    assert "item-copy-data" in content


def test_editing_an_item_does_not_offer_it(client, owner, source):
    """Copying into an item that exists would overwrite a description
    someone chose on purpose."""
    client.force_login(owner)
    url = reverse("master_edit", args=["items", source.pk])
    assert "data-copy-source" not in client.get(url).content.decode()


def test_a_customer_page_does_not_offer_it(client, owner):
    client.force_login(owner)
    content = client.get(reverse("master_create", args=["customers"])).content.decode()
    assert "data-copy-source" not in content


def test_the_receiving_dialog_offers_it(client, owner, source):
    client.force_login(owner)
    content = client.get(reverse("document_create", args=["RECEIVING"])).content.decode()
    assert "data-copy-source" in content
    assert "item-copy-data" in content


def test_the_receiving_page_still_has_its_new_item_button(client, owner, source):
    """R49 restored: the button that opens the dialog sits with Add row."""
    client.force_login(owner)
    content = client.get(reverse("document_create", args=["RECEIVING"])).content.decode()
    assert "data-open-item-modal" in content
    assert '<dialog id="item-modal"' in content


def test_the_detailed_tick_is_gone(client, owner, source):
    """The owner asked for it to be removed completely."""
    client.force_login(owner)
    content = client.get(reverse("document_create", args=["RECEIVING"])).content.decode()
    assert "data-detailed-toggle" not in content
    assert "Detailed" not in content


def test_a_sale_offers_neither(client, owner, source):
    """R49: sales staff pick items, they do not create them."""
    client.force_login(owner)
    content = client.get(reverse("document_create", args=["SALE"])).content.decode()
    assert "data-copy-source" not in content
    assert "data-open-item-modal" not in content
