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
