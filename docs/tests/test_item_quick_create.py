"""R49: staff had to abandon a half-typed receiving to add an unknown item.
The Receiving form now opens the FULL ItemForm in a dialog — D67 auto-code
and D81 price rules apply, never a simplified parallel form — and hands
the new item back to the pickers without a page reload."""

import pytest
from django.urls import reverse

from catalog.models import Item
from core.models import AuditLog, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(client):
    user = User.objects.create_user("boss", password="pw", role=User.Role.OWNER)
    client.force_login(user)
    return user


ITEM_POST = {
    "name": "Amoxil", "generic_name": "Amoxicillin", "category": "DRUG",
    # D136: a drug must carry its strength
    "strength": "500mg",
    "is_batch_tracked": "on", "has_expiry": "on", "base_unit": "pack",
    "maintained_price": "150.00", "pricing_mode": "MANUAL", "is_active": "on",
}


def test_quick_create_returns_what_the_pickers_need(client, owner):
    response = client.post(reverse("item_quick_create"), ITEM_POST)
    assert response.status_code == 200
    data = response.json()
    item = Item.objects.get(pk=data["id"])
    assert item.code == "ITM-0001"        # D67: assigned, never typed
    assert data["label"] == str(item)     # generic-first naming (R48)
    assert data["price"] == "150.00"
    assert data["baseUnit"] == "pack"
    assert data["vatExempt"] == "0"


def test_quick_create_is_audited_like_the_master_form(client, owner):
    client.post(reverse("item_quick_create"), ITEM_POST)
    entry = AuditLog.objects.get(action="MASTER_CREATE", entity="Item")
    assert entry.after["name"] == "Amoxil"


def test_invalid_data_re_renders_the_fields_with_errors(client, owner):
    response = client.post(reverse("item_quick_create"),
                           ITEM_POST | {"maintained_price": ""})
    assert response.status_code == 400
    assert "field-error" in response.content.decode()
    assert not Item.objects.exists()


def test_receiving_form_offers_the_modal(client, owner):
    content = client.get(
        reverse("document_create", args=["RECEIVING"])).content.decode()
    assert "item-modal" in content
    assert reverse("item_quick_create") in content


def test_sale_form_keeps_the_master_flow(client, owner):
    """Scope is the receiving desk (R49) — sales staff pick, they don't create."""
    content = client.get(
        reverse("document_create", args=["SALE"])).content.decode()
    assert "item-modal" not in content
