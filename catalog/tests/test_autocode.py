"""Master codes are auto-assigned like document numbers; explicit codes
(legacy migration via CSV) still win. See AutoCodeModel."""

import io

import pytest

from catalog.importers import import_customers, import_items
from catalog.models import Customer, Item, Supplier

pytestmark = pytest.mark.django_db


def as_file(text: str) -> io.BytesIO:
    return io.BytesIO(text.encode("utf-8"))


def test_blank_codes_get_sequential_prefixed_numbers():
    first = Item.objects.create(name="Paracetamol", base_unit="tablet")
    second = Item.objects.create(name="Gloves", base_unit="pair")
    assert first.code == "ITM-0001"
    assert second.code == "ITM-0002"


def test_each_model_has_its_own_sequence():
    assert Item.objects.create(name="A").code == "ITM-0001"
    assert Customer.objects.create(name="B").code == "CUS-0001"
    assert Supplier.objects.create(name="C").code == "SUP-0001"


def test_explicit_code_wins_and_is_never_overwritten():
    item = Item.objects.create(code="LEGACY-9", name="Old stock item")
    assert item.code == "LEGACY-9"
    item.name = "Renamed"
    item.save()
    assert item.code == "LEGACY-9"


def test_auto_code_skips_numbers_taken_by_legacy_codes():
    Item.objects.create(code="ITM-0002", name="Imported with legacy code")
    a = Item.objects.create(name="First auto")
    b = Item.objects.create(name="Second auto")
    assert a.code == "ITM-0001"
    assert b.code == "ITM-0003"  # 0002 was taken; sequence walks past it


def test_saving_existing_row_does_not_consume_numbers():
    item = Item.objects.create(name="Stable")
    item.name = "Stable renamed"
    item.save()
    assert Item.objects.create(name="Next").code == "ITM-0002"


def test_csv_import_with_blank_code_auto_assigns():
    result = import_customers(as_file("code,name\n,Walk-in Clinic\nC900,Legacy Clinic\n"))
    assert result.errors == []
    assert result.created == 2
    assert Customer.objects.filter(code="CUS-0001", name="Walk-in Clinic").exists()
    assert Customer.objects.filter(code="C900", name="Legacy Clinic").exists()


def test_csv_import_without_code_column_auto_assigns():
    result = import_items(as_file(
        "name,category,base_unit\nAmoxicillin,DRUG,pack\n"
    ))
    assert result.errors == []
    assert Item.objects.get(name="Amoxicillin").code == "ITM-0001"
