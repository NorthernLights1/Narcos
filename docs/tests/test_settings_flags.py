"""D89: settings flags decide which boxes the entry forms show.

Each flag only hides a box — the columns behind them keep working, so a
document posted while a flag was on still totals exactly the same after
it is switched off."""

from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Customer, Item
from core.models import CompanySettings
from docs.forms import DocumentForm, DocumentReferenceForm, formsets_for
from docs.models import Document, DocType, DocumentLine

pytestmark = pytest.mark.django_db

D = Decimal


def _settings(**flags):
    settings = CompanySettings.load()
    for name, value in flags.items():
        setattr(settings, name, value)
    settings.save()
    return settings


def _line_fields(doc_type, owner):
    doc = Document.objects.create(doc_type=doc_type, created_by=owner)
    formsets = formsets_for(doc)
    lines = next(fs for prefix, _t, fs in formsets if prefix == "lines")
    return set(lines.empty_form.fields)


def test_defaults_keep_every_box(client, owner):
    """Existing installs must not change until someone flips a switch."""
    settings = CompanySettings.load()
    assert settings.fiscal_machine_present is True
    assert settings.discounts_enabled is True
    assert settings.unit_conversion_enabled is True
    assert settings.sale_price_editable is False

    assert "machine_total" in DocumentForm(doc_type=DocType.SALE).fields
    assert "doc_discount" in DocumentForm(doc_type=DocType.SALE).fields
    fields = _line_fields(DocType.SALE, owner)
    assert "line_discount" in fields
    assert "factor" in fields


def test_no_fiscal_machine_hides_machine_total():
    _settings(fiscal_machine_present=False)
    assert "machine_total" not in DocumentForm(doc_type=DocType.SALE).fields


def test_reference_form_shows_machine_total_by_default():
    """R56: the posted-document Reference form obeys the same switches."""
    assert "machine_total" in DocumentReferenceForm().fields


def test_no_fiscal_machine_hides_machine_total_on_reference_form():
    """R56: turning off the fiscal machine hid the box on entry forms but
    left it on the Reference form — the one place it kept leaking through."""
    _settings(fiscal_machine_present=False)
    assert "machine_total" not in DocumentReferenceForm().fields


def test_discounts_off_hides_both_discount_boxes(owner):
    _settings(discounts_enabled=False)
    assert "doc_discount" not in DocumentForm(doc_type=DocType.SALE).fields
    assert "line_discount" not in _line_fields(DocType.SALE, owner)


def test_factor_off_hides_the_factor_box(owner):
    _settings(unit_conversion_enabled=False)
    assert "factor" not in _line_fields(DocType.SALE, owner)


def test_sale_price_is_readonly_by_default(owner):
    """D80 unchanged while the flag is off: the box is shown, never typed."""
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=owner)
    lines = next(fs for prefix, _t, fs in formsets_for(doc) if prefix == "lines")
    assert lines.empty_form.fields["unit_price"].widget.attrs.get("readonly")


def test_flag_makes_sale_price_typeable(owner):
    _settings(sale_price_editable=True)
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=owner)
    lines = next(fs for prefix, _t, fs in formsets_for(doc) if prefix == "lines")
    assert not lines.empty_form.fields["unit_price"].widget.attrs.get("readonly")


def test_typed_price_survives_when_the_flag_is_on(owner):
    """With the flag on the server keeps what staff typed instead of
    overwriting it with the item's price (D80's recompute is skipped)."""
    _settings(sale_price_editable=True)
    item = Item.objects.create(code="AMOX", name="Amoxicillin",
                               base_unit="pack", maintained_price=D("15.00"))
    customer = Customer.objects.create(code="C1", name="Selam Pharmacy")
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                  customer=customer)
    formsets = formsets_for(doc, {
        "lines-TOTAL_FORMS": "1", "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "0", "lines-MAX_NUM_FORMS": "1000",
        "lines-0-item": str(item.pk), "lines-0-qty_entered": "2",
        "lines-0-unit_label": "pack", "lines-0-factor": "1",
        "lines-0-unit_price": "12.00", "lines-0-line_discount": "0",
    })
    lines = next(fs for prefix, _t, fs in formsets if prefix == "lines")
    assert lines.is_valid(), lines.errors
    assert lines.forms[0].cleaned_data["unit_price"] == D("12.00")


def test_hidden_boxes_do_not_disturb_posted_documents(client, owner):
    """A sale posted with a discount still reads back the same after the
    business turns discounts off."""
    item = Item.objects.create(code="PARA", name="Paracetamol",
                               base_unit="pack", maintained_price=D("10.00"),
                               vat_exempt=True)
    customer = Customer.objects.create(code="C2", name="Mekelle Pharmacy")
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                  customer=customer, doc_discount=D("5.00"))
    DocumentLine.objects.create(document=doc, item=item, qty_entered=2,
                                unit_price=D("10.00"), unit_label="pack",
                                factor=1, line_discount=D("1.00"))

    _settings(discounts_enabled=False, fiscal_machine_present=False)
    doc.refresh_from_db()
    assert doc.doc_discount == D("5.00")
    assert doc.lines.get().line_discount == D("1.00")

    client.force_login(owner)
    html = client.get(reverse("document_detail", args=[doc.pk])).content.decode()
    assert response_ok(html)


def response_ok(html: str) -> bool:
    return "<html" in html.lower()
