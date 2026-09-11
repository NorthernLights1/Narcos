"""D137: a filter the user set stays set.

D131 settled that there is no auto-login, so staff sign in every morning. A
session-backed memory therefore resets every day, and the same filter has to be
retyped every day. This remembers it against the user row instead.

Two boundaries matter more than the happy path. **An explicit filter always
wins**, or the screen argues with the person using it. And **clearing a filter
must stick**: the filter form submits its boxes even when they are empty, so a
blank submission is a deliberate "show me everything", not an absence of
instruction.
"""

import pytest
from django.urls import reverse

from catalog.models import Customer, Supplier
from core.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


@pytest.fixture
def clerk():
    return User.objects.create_user("clerk", password="pw", role=User.Role.EMPLOYEE)


@pytest.fixture
def parties(db):
    Customer.objects.create(code="C001", name="Selam Pharmacy")
    Supplier.objects.create(code="S001", name="Addis Pharma")


def test_a_filter_survives_to_the_next_visit(client, owner, parties):
    client.force_login(owner)
    client.get(reverse("document_list"), {"type": "SALE"})

    response = client.get(reverse("document_list"))
    assert response.context["selected_type"] == "SALE"


def test_it_survives_logging_out_and_back_in(client, owner, parties):
    """The whole point: the client's machine is switched off overnight and
    nobody is logged in automatically, so a session would lose this daily."""
    client.force_login(owner)
    client.get(reverse("document_list"), {"type": "SALE"})
    client.logout()

    client.force_login(owner)
    response = client.get(reverse("document_list"))
    assert response.context["selected_type"] == "SALE"


def test_an_explicit_filter_beats_the_remembered_one(client, owner, parties):
    client.force_login(owner)
    client.get(reverse("document_list"), {"type": "SALE"})

    response = client.get(reverse("document_list"), {"type": "RECEIVING"})
    assert response.context["selected_type"] == "RECEIVING"


def test_clearing_a_filter_sticks(client, owner, parties):
    """The form submits its boxes even when empty, so a blank submission is a
    deliberate "show me everything" and must not be overruled by the memory."""
    client.force_login(owner)
    client.get(reverse("document_list"), {"type": "SALE"})
    client.get(reverse("document_list"), {"type": ""})

    response = client.get(reverse("document_list"))
    assert response.context["selected_type"] == ""


def test_one_user_does_not_inherit_another_user_s_filter(client, owner, clerk,
                                                         parties):
    client.force_login(owner)
    client.get(reverse("document_list"), {"type": "SALE"})
    client.logout()

    client.force_login(clerk)
    response = client.get(reverse("document_list"))
    assert response.context["selected_type"] == ""


def test_the_inventory_search_is_remembered_too(client, owner):
    client.force_login(owner)
    client.get(reverse("inventory_list"), {"q": "amox"})

    response = client.get(reverse("inventory_list"))
    assert response.context["query"] == "amox"


def test_a_report_period_is_remembered(client, owner):
    client.force_login(owner)
    client.get(reverse("report_detail", args=["stock-on-hand"]),
               {"period": "custom", "start": "2026-01-01", "end": "2026-01-31"})

    response = client.get(reverse("report_detail", args=["stock-on-hand"]))
    assert response.context["period"] == "custom"
    assert response.context["start"].isoformat() == "2026-01-01"


def test_two_screens_keep_separate_memories(client, owner, parties):
    """Scoped per screen, or filtering documents would silently re-filter
    inventory."""
    client.force_login(owner)
    client.get(reverse("inventory_list"), {"q": "amox"})
    client.get(reverse("document_list"), {"q": "SI-0001"})

    assert client.get(reverse("inventory_list")).context["query"] == "amox"
    assert client.get(reverse("document_list")).context["query"] == "SI-0001"
