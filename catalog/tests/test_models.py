"""P1 model constraints: unique codes, D26 uniqueness."""

import pytest
from django.db import IntegrityError

from catalog.models import Customer, Item

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




