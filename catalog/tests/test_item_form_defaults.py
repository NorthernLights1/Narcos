"""R59/R60: entering an item should assume this trade's normal case — a
VAT-exempt drug — and offer the common units in a visible dropdown that
still accepts a typed custom unit ("Other — type it below")."""

import pytest
from django import forms as django_forms

from catalog.forms import OTHER_UNIT, ItemForm
from catalog.models import Item

pytestmark = pytest.mark.django_db

BASE = {
    "name": "Amoxil", "category": "DRUG", "is_batch_tracked": "on",
    "has_expiry": "on", "base_unit": "pack", "maintained_price": "150.00",
    "pricing_mode": "MANUAL", "is_active": "on",
}


def test_new_item_defaults_to_vat_exempt():
    """R59: medicines are VAT-exempt by law and the default category is
    DRUG — the box starts ticked instead of demanding a tick every time."""
    assert ItemForm().fields["vat_exempt"].initial is True


def test_editing_keeps_the_saved_vat_flag():
    item = Item.objects.create(code="X1", name="Gloves", category="SUPPLY",
                               base_unit="pair", vat_exempt=False,
                               maintained_price=10)
    assert ItemForm(instance=item).initial["vat_exempt"] is False


def test_base_unit_is_a_dropdown_of_common_units():
    widget = ItemForm().fields["base_unit"].widget
    assert isinstance(widget, django_forms.Select)
    values = [value for value, _label in widget.choices]
    assert "tablet" in values
    assert OTHER_UNIT in values


def test_saved_custom_unit_still_appears_in_the_dropdown():
    item = Item.objects.create(code="X2", name="ORS", base_unit="pack of 10",
                               maintained_price=5)
    values = [v for v, _l in ItemForm(instance=item).fields["base_unit"].widget.choices]
    assert "pack of 10" in values


def test_other_unit_requires_the_typed_text():
    form = ItemForm(BASE | {"base_unit": OTHER_UNIT, "base_unit_other": ""})
    assert not form.is_valid()
    assert "base_unit_other" in form.errors


def test_other_unit_saves_the_typed_text():
    form = ItemForm(BASE | {"base_unit": OTHER_UNIT,
                            "base_unit_other": "pack of 25"})
    assert form.is_valid(), form.errors
    assert form.save().base_unit == "pack of 25"
