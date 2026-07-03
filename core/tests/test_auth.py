import pytest
from django.urls import reverse

from core.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_user(username="owner", password="pw12345678", role=User.Role.OWNER)


@pytest.fixture
def employee():
    return User.objects.create_user(username="emp", password="pw12345678", role=User.Role.EMPLOYEE)


def test_login_page_renders(client):
    response = client.get(reverse("login"))
    assert response.status_code == 200
    assert b"Log in" in response.content


def test_dashboard_requires_login(client):
    response = client.get(reverse("dashboard"))
    assert response.status_code == 302
    assert reverse("login") in response.url


def test_dashboard_shows_ethiopian_date(client, owner):
    client.force_login(owner)
    response = client.get(reverse("dashboard"))
    assert response.status_code == 200
    assert b" EC" in response.content  # D19: Ethiopian date visible


def test_owner_sees_settings_link_employee_does_not(client, owner, employee):
    client.force_login(owner)
    assert reverse("company_settings").encode() in client.get(reverse("dashboard")).content
    client.force_login(employee)
    assert reverse("company_settings").encode() not in client.get(reverse("dashboard")).content


def test_role_property(owner, employee):
    assert owner.is_owner
    assert not employee.is_owner
