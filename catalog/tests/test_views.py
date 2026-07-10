"""P1 views: CRUD audited (D47), margin fields hidden from employees (D33),
duplicate search works (D26)."""

import pytest
from django.urls import reverse

from catalog.models import Customer, Item
from core.models import AuditLog, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(client):
    user = User.objects.create_user("boss", password="pw", role=User.Role.OWNER)
    client.force_login(user)
    return user


@pytest.fixture
def employee(client):
    user = User.objects.create_user("staff", password="pw", role=User.Role.EMPLOYEE)
    client.force_login(user)
    return user


ITEM_POST = {
    "name": "Amoxicillin 500mg", "category": "DRUG",
    "is_batch_tracked": "on", "has_expiry": "on", "base_unit": "pack of 10",
    "maintained_price": "150.00", "pricing_mode": "MANUAL", "is_active": "on",
    # units formset management form (no units)
    "units-TOTAL_FORMS": "0", "units-INITIAL_FORMS": "0",
    "units-MIN_NUM_FORMS": "0", "units-MAX_NUM_FORMS": "1000",
}


def test_create_item_writes_audit_row(client, owner):
    response = client.post(reverse("master_create", args=["items"]), ITEM_POST)
    assert response.status_code == 302
    item = Item.objects.get(name="Amoxicillin 500mg")
    assert item.code == "ITM-0001"  # auto-assigned, never typed
    entry = AuditLog.objects.get(action="MASTER_CREATE", entity="Item")
    assert entry.after["code"] == "ITM-0001"


def test_edit_item_audits_only_the_diff(client, owner):
    client.post(reverse("master_create", args=["items"]), ITEM_POST)
    item = Item.objects.get(name="Amoxicillin 500mg")
    changed = ITEM_POST | {"maintained_price": "175.00"}
    client.post(reverse("master_edit", args=["items", item.pk]), changed)
    entry = AuditLog.objects.get(action="MASTER_UPDATE", entity="Item")
    assert entry.before == {"maintained_price": "150"}
    assert entry.after == {"maintained_price": "175"}


def test_employee_item_form_hides_margin_fields(client, employee):
    response = client.get(reverse("master_create", args=["items"]))
    content = response.content.decode()
    assert "min_margin_pct" not in content  # D33
    assert "auto_margin_pct" not in content
    assert "maintained_price" in content  # selling price is fine


def test_employee_can_create_master_data(client, employee):
    response = client.post(
        reverse("master_create", args=["customers"]),
        {"name": "Pharmacy A"},
    )
    assert response.status_code == 302
    assert Customer.objects.filter(code="CUS-0001", name="Pharmacy A").exists()


def test_duplicate_search_returns_matches(client, owner):
    Customer.objects.create(code="C001", name="Selam Pharmacy")
    response = client.get(
        reverse("master_search", args=["customers"]), {"name": "selam"}
    )
    assert "Selam Pharmacy" in response.content.decode()


def test_duplicate_search_ignores_short_queries(client, owner):
    Customer.objects.create(code="C001", name="Selam Pharmacy")
    response = client.get(reverse("master_search", args=["customers"]), {"name": "s"})
    assert "Selam" not in response.content.decode()


def test_unknown_kind_404s(client, owner):
    assert client.get("/master/nonsense/").status_code == 404


@pytest.mark.parametrize("kind", [
    "items", "customers", "suppliers", "accounts", "expense-categories", "fixed-assets",
])
def test_every_list_page_renders(client, owner, kind):
    Customer.objects.create(code="C001", name="Pharmacy A")
    assert client.get(reverse("master_list", args=[kind])).status_code == 200


def test_item_with_units_saves_and_lists(client, owner):
    post = ITEM_POST | {
        "units-TOTAL_FORMS": "1",
        "units-0-unit_label": "carton", "units-0-factor_to_base": "12",
    }
    response = client.post(reverse("master_create", args=["items"]), post)
    assert response.status_code == 302
    item = Item.objects.get(name="Amoxicillin 500mg")
    assert item.units.get().factor_to_base == 12
