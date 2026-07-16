"""Settings-aware report visibility: reports that can never have data under
the company's configuration disappear from the hub (and 404 directly)
instead of sitting there forever empty. Flip the setting and they return —
nothing is deleted."""

import pytest
from django.urls import reverse

from core.models import CompanySettings, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


def _settings(**overrides):
    settings = CompanySettings.load()
    for key, value in overrides.items():
        setattr(settings, key, value)
    settings.save()
    return settings


def test_withholding_payable_hidden_when_not_an_agent(client, owner):
    _settings(withholding_on_purchases=False)
    client.force_login(owner)
    hub = client.get(reverse("report_hub")).content.decode()
    assert "withholding-payable" not in hub
    assert client.get(
        reverse("report_detail", args=["withholding-payable"])
    ).status_code == 404


def test_withholding_payable_returns_when_enabled(client, owner):
    _settings(withholding_on_purchases=True)
    client.force_login(owner)
    hub = client.get(reverse("report_hub")).content.decode()
    assert "withholding-payable" in hub
    assert client.get(
        reverse("report_detail", args=["withholding-payable"])
    ).status_code == 200


def test_withholding_received_follows_sales_flag(client, owner):
    _settings(withholding_on_sales=False)
    client.force_login(owner)
    assert "withholding-received" not in client.get(reverse("report_hub")).content.decode()
    _settings(withholding_on_sales=True)
    assert "withholding-received" in client.get(reverse("report_hub")).content.decode()


def test_vat_summary_hidden_without_tax_regime(client, owner):
    _settings(tax_regime=CompanySettings.TaxRegime.NONE)
    client.force_login(owner)
    hub = client.get(reverse("report_hub")).content.decode()
    assert "/reports/vat/" not in hub
    assert client.get(reverse("report_detail", args=["vat"])).status_code == 404


def test_vat_summary_visible_under_vat_regime(client, owner):
    _settings(tax_regime=CompanySettings.TaxRegime.VAT)
    client.force_login(owner)
    assert "/reports/vat/" in client.get(reverse("report_hub")).content.decode()


def test_hub_grouped_with_statement_pinned(client, owner):
    client.force_login(owner)
    hub = client.get(reverse("report_hub")).content.decode()
    for heading in ("Stock", "Sales", "Receivables", "Money"):
        assert heading in hub
    assert reverse("statement") in hub
