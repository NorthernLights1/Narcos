"""R48: this trade reads medicines by generic name, so the generic leads
everywhere an item is named — `Item.__str__` drives every dropdown in the
app and the D100 refusal messages, and the items list gains a Generic
name column (it was searchable but invisible)."""

import pytest
from django.urls import reverse

from catalog.models import Item
from core.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(client):
    user = User.objects.create_user("boss", password="pw", role=User.Role.OWNER)
    client.force_login(user)
    return user


def test_str_reads_generic_first_with_brand_in_brackets():
    item = Item(code="AMOX", name="Amoxil", generic_name="Amoxicillin")
    assert str(item) == "AMOX — Amoxicillin (Amoxil)"


def test_str_without_generic_keeps_the_brand():
    item = Item(code="PARA", name="Paracetamol")
    assert str(item) == "PARA — Paracetamol"


def test_items_list_shows_generic_name_column(client, owner):
    Item.objects.create(code="AMOX", name="Amoxil",
                        generic_name="Amoxicillin", base_unit="pack")
    content = client.get(reverse("master_list", args=["items"])).content.decode()
    assert "Generic name" in content
    assert "Amoxicillin" in content


def test_list_headers_read_as_labels_not_field_names(client, owner):
    """The header must say "Generic name", not leak `generic_name`."""
    content = client.get(reverse("master_list", args=["items"])).content.decode()
    assert "generic_name" not in content
    assert "maintained_price" not in content
    assert "Selling price" in content


# --- D134: strength is printed everywhere and shown nowhere -----------------
#
# `full_description` has carried strength onto the invoice, the sales
# attachment and the picking list since 940b280 (round 4, in v1.1.0). No
# screen has ever shown it. Two items differing only by strength are therefore
# indistinguishable in every picker and on the document being typed, and
# neither Master nor Inventory can search for one — which is why the size gets
# typed into the name instead, where it does show up. Fix the readers.

def test_str_carries_strength_when_the_item_has_one():
    item = Item(code="AMOX", name="Amoxil", generic_name="Amoxicillin",
                strength="500mg")
    assert str(item) == "AMOX — Amoxicillin (Amoxil), 500mg"


def test_str_without_a_generic_still_carries_strength():
    item = Item(code="PARA", name="Paracetamol", strength="500mg")
    assert str(item) == "PARA — Paracetamol, 500mg"


def test_str_is_unchanged_when_there_is_no_strength():
    """58 of 201 real items have none, so the blank case is the common one and
    must not leave a dangling separator."""
    item = Item(code="AMOX", name="Amoxil", generic_name="Amoxicillin")
    assert str(item) == "AMOX — Amoxicillin (Amoxil)"


def test_items_list_shows_a_strength_column(client, owner):
    Item.objects.create(code="AMOX", name="Amoxil", generic_name="Amoxicillin",
                        strength="500mg", base_unit="pack")
    content = client.get(reverse("master_list", args=["items"])).content.decode()
    assert "Strength" in content
    assert "500mg" in content
    assert "strength" not in content  # the label, never the field name


def test_items_search_finds_an_item_by_its_strength(client, owner):
    Item.objects.create(code="AMOX", name="Amoxil", generic_name="Amoxicillin",
                        strength="500mg", base_unit="pack")
    Item.objects.create(code="AMOX2", name="Amoxil", generic_name="Amoxicillin",
                        strength="250mg", base_unit="pack")
    url = reverse("master_list", args=["items"])
    content = client.get(url, {"q": "250mg"}).content.decode()
    assert "AMOX2" in content
    assert "AMOX-" not in content.replace("AMOX2", "")
