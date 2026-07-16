"""Rule: every item must carry a usable price — a maintained price > 0, or
AUTO mode with a margin %. Enforced at the form and CSV-import boundaries so
the CN-000002 mistake (item created priceless, price typed ad hoc on the
document) cannot recur."""

from decimal import Decimal

import pytest

from catalog.forms import ItemForm
from catalog.importers import import_items
from catalog.models import Item

pytestmark = pytest.mark.django_db

D = Decimal

BASE = {
    "name": "Exam Gloves",
    "category": Item.Category.SUPPLY,
    "base_unit": "pair",
    "is_batch_tracked": False,
    "has_expiry": False,
    "reorder_level": 0,
    "pricing_mode": Item.PricingMode.MANUAL,
}


def test_manual_item_requires_positive_price():
    form = ItemForm(BASE | {"maintained_price": "0"})
    assert not form.is_valid()
    assert "maintained_price" in form.errors


def test_manual_item_with_price_is_valid():
    form = ItemForm(BASE | {"maintained_price": "10.00"})
    assert form.is_valid(), form.errors


def test_auto_item_needs_no_maintained_price():
    form = ItemForm(BASE | {
        "pricing_mode": Item.PricingMode.AUTO,
        "auto_margin_pct": "40",
        "maintained_price": "0",
    })
    assert form.is_valid(), form.errors


def test_auto_item_still_requires_margin():
    form = ItemForm(BASE | {
        "pricing_mode": Item.PricingMode.AUTO,
        "maintained_price": "0",
    })
    assert not form.is_valid()
    assert "auto_margin_pct" in form.errors


def test_employee_edit_of_auto_item_not_blocked():
    """Employees don't see pricing_mode (D33); editing an AUTO item must not
    demand a maintained price they can't know about."""
    item = Item.objects.create(
        code="AUTO", name="Auto priced", base_unit="unit",
        is_batch_tracked=False, has_expiry=False,
        pricing_mode=Item.PricingMode.AUTO, auto_margin_pct=D("40"),
        maintained_price=D("0"),
    )
    form = ItemForm(
        BASE | {"name": "Auto priced", "maintained_price": "0"},
        instance=item, is_owner=False,
    )
    assert form.is_valid(), form.errors


def test_import_rejects_priceless_row():
    import io
    csv_file = io.BytesIO(
        "name,category,base_unit,maintained_price\n"
        "Gauze,SUPPLY,roll,0\n".encode()
    )
    result = import_items(csv_file)
    assert result.errors
    assert not Item.objects.filter(name="Gauze").exists()
