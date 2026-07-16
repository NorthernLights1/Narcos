"""AR/AP balances as of a date (client request): one row per party with a
non-zero balance on the chosen day — a snapshot, deliberately separate from
aging (no due dates, no buckets). Every figure must tie out with the same
party's statement closing balance for the same date."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from catalog.models import Account, Customer, Item, Supplier
from core.models import User
from reports.tests.test_statement import (
    credit_sale,
    customer_payment,
    receive,
)

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def owner():
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


@pytest.fixture
def cash():
    return Account.objects.create(name="Cash drawer", type=Account.Type.CASH)


@pytest.fixture
def customer():
    return Customer.objects.create(code="C001", name="Selam Pharmacy")


@pytest.fixture
def supplier():
    return Supplier.objects.create(code="S001", name="Addis Pharma")


@pytest.fixture
def drug():
    return Item.objects.create(
        code="AMOX", name="Amoxicillin", base_unit="pack",
        is_batch_tracked=True, has_expiry=True, vat_exempt=True,
        maintained_price=D("15.00"),
    )


def _params(**extra):
    today = timezone.localdate().isoformat()
    params = {"period": "custom", "start": today, "end": today}
    params.update(extra)
    return params


def test_ar_balances_per_customer(client, owner, cash, customer, supplier, drug):
    receive(owner, supplier, drug)
    sale = credit_sale(owner, customer, drug, qty=2, price="15.00")  # +30
    customer_payment(owner, customer, sale, cash, "10.00")           # -10
    client.force_login(owner)
    response = client.get(reverse("report_detail", args=["ar-balances"]),
                          _params())
    rows = response.context["rows"]
    assert rows == [["C001", "Selam Pharmacy", D("20.00")]]
    assert response.context["total"][-1] == D("20.00")


def test_settled_customer_omitted(client, owner, cash, customer, supplier, drug):
    receive(owner, supplier, drug)
    sale = credit_sale(owner, customer, drug, qty=2, price="15.00")
    customer_payment(owner, customer, sale, cash, "30.00")
    client.force_login(owner)
    response = client.get(reverse("report_detail", args=["ar-balances"]),
                          _params())
    assert response.context["rows"] == []


def test_as_of_date_excludes_later_activity(client, owner, cash, customer,
                                            supplier, drug):
    receive(owner, supplier, drug)
    credit_sale(owner, customer, drug, qty=2, price="15.00")  # posted today
    yesterday = (timezone.localdate() - datetime.timedelta(days=1)).isoformat()
    client.force_login(owner)
    response = client.get(
        reverse("report_detail", args=["ar-balances"]),
        _params(start=yesterday, end=yesterday),
    )
    assert response.context["rows"] == []


def test_ap_balances_per_supplier(client, owner, supplier, drug):
    receive(owner, supplier, drug, qty=10, cost="10.00")  # we owe 100
    client.force_login(owner)
    response = client.get(reverse("report_detail", args=["ap-balances"]),
                          _params())
    assert response.context["rows"] == [["S001", "Addis Pharma", D("100.00")]]


def test_balance_matches_statement_closing(client, owner, cash, customer,
                                           supplier, drug):
    receive(owner, supplier, drug)
    sale = credit_sale(owner, customer, drug, qty=2, price="15.00")
    customer_payment(owner, customer, sale, cash, "12.50")
    client.force_login(owner)
    statement = client.get(
        reverse("statement"),
        _params(party_type="customer", party=customer.pk),
    )
    report = client.get(reverse("report_detail", args=["ar-balances"]),
                        _params())
    assert report.context["rows"][0][2] == statement.context["closing"]


def test_csv_export(client, owner, cash, customer, supplier, drug):
    receive(owner, supplier, drug)
    credit_sale(owner, customer, drug)
    client.force_login(owner)
    response = client.get(reverse("report_detail", args=["ar-balances"]),
                          _params(format="csv"))
    assert response["Content-Type"] == "text/csv"
    assert "Selam Pharmacy" in response.content.decode()
