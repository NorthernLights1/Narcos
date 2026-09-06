"""P1 model constraints: unique codes, unit factor rules (D62), D26 uniqueness."""

import pytest
from django.db import IntegrityError

from catalog.models import Customer, Item, ItemUnit

pytestmark = pytest.mark.django_db


def make_item(code="AMOX-500", **overrides) -> Item:
    fields = {"code": code, "name": "Amoxicillin 500mg", "base_unit": "pack of 10"}
    fields.update(overrides)
    return Item.objects.create(**fields)


def test_item_code_unique():
    make_item()
    with pytest.raises(IntegrityError):
        make_item(name="Different name")


def test_customer_code_unique():
    Customer.objects.create(code="C001", name="Pharmacy A")
    with pytest.raises(IntegrityError):
        Customer.objects.create(code="C001", name="Pharmacy B")


def test_unit_factor_must_exceed_one():
    item = make_item()
    with pytest.raises(IntegrityError):
        ItemUnit.objects.create(item=item, unit_label="carton", factor_to_base=1)


def test_unit_label_unique_per_item():
    item = make_item()
    ItemUnit.objects.create(item=item, unit_label="carton", factor_to_base=12)
    with pytest.raises(IntegrityError):
        ItemUnit.objects.create(item=item, unit_label="carton", factor_to_base=24)


def test_same_unit_label_ok_on_other_item():
    first = make_item()
    second = make_item(code="PARA-500", name="Paracetamol")
    ItemUnit.objects.create(item=first, unit_label="carton", factor_to_base=12)
    ItemUnit.objects.create(item=second, unit_label="carton", factor_to_base=24)
