"""D139: one screen for receiving and for the new item that arrived with it.

R49 put the full `ItemForm` in a dialog so the receiving desk could create an
item mid-document. The client asked for it inline instead, behind a **detailed**
tick, because goods arrive with brands that are not in the catalogue and opening
a dialog for each one breaks the rhythm of typing a delivery note.

Two things this pins.

**The panel replaces the dialog, it does not join it.** Two entry surfaces for
one form is the risk worth avoiding, and a single unified interface is what was
asked for.

**Defaults come from a nominated sibling item, never from brand and strength
defaulted independently** (D132). Independent defaults can name a combination
that does not exist; a real sibling supplies a valid brand, strength, form and
unit together.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Item, Supplier
from core.models import User

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def owner():
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


@pytest.fixture
def supplier():
    return Supplier.objects.create(code="S001", name="Addis Pharma")


@pytest.fixture
def sibling(db):
    return Item.objects.create(
        code="IBU1", name="Gofen", generic_name="Ibuprofen", strength="400mg",
        dosage_form="tablet", pack_description="strip of 10", base_unit="pack",
        category=Item.Category.DRUG, is_batch_tracked=True, has_expiry=True,
        vat_exempt=True, maintained_price=D("150.00"),
    )


def _receiving(client, owner):
    client.force_login(owner)
    return client.get(reverse("document_create", args=["RECEIVING"]))


def test_the_item_form_is_inline_not_in_a_dialog(client, owner, supplier):
    content = _receiving(client, owner).content.decode()
    assert 'id="item-inline"' in content
    assert 'id="item-modal"' not in content


def test_the_panel_is_collapsed_behind_a_detailed_tick(client, owner, supplier):
    """The client's worry was that an always-open item form would make the
    receiving page ugly. The tick is the answer: nothing shows until asked."""
    content = _receiving(client, owner).content.decode()
    assert "data-detailed-toggle" in content
    assert "Detailed" in content


def test_the_panel_runs_the_full_item_form(client, owner, supplier):
    """D108: never a simplified parallel form, or D67 auto-codes and D81 price
    rules stop applying to items created here."""
    content = _receiving(client, owner).content.decode()
    for field in ("name", "generic_name", "strength", "category",
                  "maintained_price", "base_unit", "pack_description"):
        assert f'name="{field}"' in content


def test_a_sibling_item_can_be_nominated_to_copy_from(client, owner, supplier,
                                                      sibling):
    response = _receiving(client, owner)
    assert 'id="item-presets"' in response.content.decode()
    assert str(sibling.pk) in response.context["item_presets"]


def test_the_preset_carries_what_a_sibling_can_validly_supply(
        client, owner, supplier, sibling):
    preset = _receiving(client, owner).context["item_presets"][str(sibling.pk)]
    assert preset["generic_name"] == "Ibuprofen"
    assert preset["dosage_form"] == "tablet"
    assert preset["base_unit"] == "pack"
    assert preset["pack_description"] == "strip of 10"
    assert preset["category"] == "DRUG"
    assert preset["vat_exempt"] is True
    assert preset["has_expiry"] is True


def test_the_preset_never_supplies_brand_or_strength(client, owner, supplier,
                                                     sibling):
    """D132: those two are what makes it a different product, so copying them
    would create a duplicate of the sibling rather than a new brand."""
    preset = _receiving(client, owner).context["item_presets"][str(sibling.pk)]
    assert "name" not in preset
    assert "strength" not in preset


def test_a_retired_item_is_not_offered_as_a_source(client, owner, supplier,
                                                   sibling):
    """D125: retiring an item has to mean something everywhere it is offered."""
    Item.objects.filter(pk=sibling.pk).update(is_active=False)
    assert _receiving(client, owner).context["item_presets"] == {}


def test_sales_still_have_no_item_panel(client, owner, supplier):
    """R49: sales staff pick items, they do not create them."""
    client.force_login(owner)
    content = client.get(reverse("document_create", args=["SALE"])).content.decode()
    assert 'id="item-inline"' not in content


def test_the_brand_box_no_longer_tells_staff_to_type_the_whole_description(
        client, owner, supplier):
    """The placeholder read "e.g. Paracetamol 500mg tablets", which instructs
    the operator to put the generic, the strength and the form into the brand
    box. That is the shape of the smearing in 06-client-data.md §3."""
    content = _receiving(client, owner).content.decode()
    assert "Paracetamol 500mg tablets" not in content
