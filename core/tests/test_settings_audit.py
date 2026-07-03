import pytest
from django.urls import reverse

from core.audit import log_event
from core.models import AuditLog, CompanySettings, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_user(username="owner", password="pw12345678", role=User.Role.OWNER)


@pytest.fixture
def employee():
    return User.objects.create_user(username="emp", password="pw12345678", role=User.Role.EMPLOYEE)


def form_data(instance):
    """Build POST data the way a browser submits the settings form."""
    data = {}
    for field in CompanySettings.AUDITED_FIELDS:
        value = getattr(instance, field)
        if isinstance(value, bool):
            if value:
                data[field] = "on"  # unchecked checkboxes are absent from POSTs
        elif value is None:
            data[field] = ""
        else:
            data[field] = str(value)
    return data


def test_owner_edits_settings_and_change_is_audited(client, owner):
    client.force_login(owner)
    url = reverse("company_settings")
    assert client.get(url).status_code == 200

    data = form_data(CompanySettings.load())
    data["near_expiry_months"] = "4"
    response = client.post(url, data)
    assert response.status_code == 302
    assert CompanySettings.load().near_expiry_months == 4

    log = AuditLog.objects.get(action="SETTINGS_UPDATE")
    assert log.actor == owner
    assert log.before == {"near_expiry_months": "6"}
    assert log.after == {"near_expiry_months": "4"}


def test_no_change_writes_no_audit_row(client, owner):
    client.force_login(owner)
    url = reverse("company_settings")
    client.post(url, form_data(CompanySettings.load()))
    assert AuditLog.objects.count() == 0


def test_employee_gets_403(client, employee):
    client.force_login(employee)
    url = reverse("company_settings")
    assert client.get(url).status_code == 403
    assert client.post(url, {}).status_code == 403


def test_anonymous_redirected_to_login(client):
    response = client.get(reverse("company_settings"))
    assert response.status_code == 302
    assert reverse("login") in response.url


def test_audit_rows_are_append_only(owner):
    row = log_event(owner, "TEST", "Thing", "1")
    row.action = "TAMPERED"
    with pytest.raises(NotImplementedError):
        row.save()
    with pytest.raises(NotImplementedError):
        row.delete()
