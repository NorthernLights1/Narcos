import pytest
from django.urls import reverse

from core.models import AuditLog, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(client):
    user = User.objects.create_user("owner", password="pw12345678", role=User.Role.OWNER)
    client.force_login(user)
    return user


@pytest.fixture
def employee(client):
    user = User.objects.create_user("staff", password="pw12345678", role=User.Role.EMPLOYEE)
    client.force_login(user)
    return user


def test_owner_can_create_employee_and_view_audit_log(client, owner):
    response = client.post(reverse("user_create"), {
        "username": "newstaff",
        "first_name": "New",
        "last_name": "Staff",
        "email": "staff@example.test",
        "role": User.Role.EMPLOYEE,
        "is_active": "on",
        "password": "pw12345678",
    })
    assert response.status_code == 302
    user = User.objects.get(username="newstaff")
    assert user.role == User.Role.EMPLOYEE
    assert AuditLog.objects.filter(action="USER_CREATE", entity="User").exists()
    assert AuditLog.objects.filter(action="USER_PASSWORD_RESET", entity_id=str(user.pk)).exists()

    response = client.get(reverse("audit_log"))
    assert response.status_code == 200
    assert "USER_CREATE" in response.content.decode()


def test_employee_cannot_open_owner_user_or_audit_screens(client, employee):
    assert client.get(reverse("user_list")).status_code == 403
    assert client.get(reverse("audit_log")).status_code == 403
