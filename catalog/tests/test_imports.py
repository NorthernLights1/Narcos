"""P1 CSV imports (§14/D57): validate-first, dirty file posts nothing,
re-import rejects duplicates, owner-only."""

import io

import pytest
from django.urls import reverse

from catalog.importers import import_customers, import_items, import_suppliers
from catalog.models import Customer, Item, Supplier
from core.models import User

pytestmark = pytest.mark.django_db


def as_file(text: str) -> io.BytesIO:
    return io.BytesIO(text.encode("utf-8"))


ITEMS_CSV = (
    "code,name,category,base_unit,vat_exempt,maintained_price,alt_units\n"
    "AMOX-500,Amoxicillin 500mg,DRUG,pack of 10,1,150.00,carton:12\n"
    "STETH-01,Stethoscope,EQUIPMENT,unit,0,900.00,\n"
)


def test_clean_items_file_imports_all():
    result = import_items(as_file(ITEMS_CSV))
    assert result.is_clean
    assert result.created == 2
    amox = Item.objects.get(code="AMOX-500")
    assert amox.vat_exempt is True
    assert amox.units.get().factor_to_base == 12
    steth = Item.objects.get(code="STETH-01")
    assert steth.is_batch_tracked is False  # equipment defaults off (D29)


def test_dirty_file_posts_nothing():
    dirty = (
        "code,name,category,base_unit\n"
        "OK-1,Fine item,DRUG,pack\n"
        "BAD-1,Bad category,POTION,pack\n"
    )
    result = import_items(as_file(dirty))
    assert not result.is_clean
    assert Item.objects.count() == 0  # the clean row must NOT slip through


def test_reimport_same_file_rejects_everything():
    assert import_items(as_file(ITEMS_CSV)).is_clean
    result = import_items(as_file(ITEMS_CSV))
    assert not result.is_clean
    assert "already exists" in " ".join(result.errors)
    assert Item.objects.count() == 2  # unchanged


def test_duplicate_code_within_file_rejected():
    dupes = (
        "code,name,category,base_unit\n"
        "X-1,First,DRUG,pack\n"
        "X-1,Second,DRUG,pack\n"
    )
    result = import_items(as_file(dupes))
    assert not result.is_clean
    assert Item.objects.count() == 0


def test_bad_alt_units_reported_with_row():
    bad = (
        "code,name,category,base_unit,alt_units\n"
        "X-1,Item,DRUG,pack,carton:one\n"
    )
    result = import_items(as_file(bad))
    assert not result.is_clean
    assert "row 2" in result.errors[0]


def test_customers_import_with_withholding_flag():
    csv_text = (
        "code,name,tin,is_withholding_agent\n"
        "C001,Mekelle Hospital PLC,001122,yes\n"
    )
    result = import_customers(as_file(csv_text))
    assert result.is_clean
    assert Customer.objects.get(code="C001").is_withholding_agent is True


def test_suppliers_import():
    result = import_suppliers(as_file("code,name\nS001,Addis Pharma\n"))
    assert result.is_clean
    assert Supplier.objects.filter(code="S001").exists()


def test_import_view_owner_only(client):
    staff = User.objects.create_user("staff", password="pw", role=User.Role.EMPLOYEE)
    client.force_login(staff)
    response = client.get(reverse("csv_import", args=["items"]))
    assert response.status_code == 403


def test_import_view_round_trip(client):
    boss = User.objects.create_user("boss", password="pw", role=User.Role.OWNER)
    client.force_login(boss)
    upload = io.BytesIO(ITEMS_CSV.encode("utf-8"))
    upload.name = "items.csv"
    response = client.post(reverse("csv_import", args=["items"]), {"file": upload})
    assert response.status_code == 302
    assert Item.objects.count() == 2


def test_not_utf8_reports_cleanly():
    result = import_items(io.BytesIO(b"\xff\xfe\x00 garbage"))
    assert not result.is_clean
