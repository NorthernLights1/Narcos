"""Catalog forms. Margin/pricing-mode fields are owner-only (D33)."""

from django import forms
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from catalog.models import (
    Account,
    Customer,
    ExpenseCategory,
    FixedAsset,
    Item,
    ItemUnit,
    Supplier,
)

OWNER_ONLY_ITEM_FIELDS = ["pricing_mode", "auto_margin_pct", "min_margin_pct"]

# Suggestions for the unit dropdowns (datalist: pick from the list or type a
# new one — D62 keeps units free-form on purpose).
COMMON_UNITS = [
    "unit", "tablet", "capsule", "strip", "blister", "bottle", "vial",
    "ampoule", "sachet", "tube", "box", "pack", "carton", "piece", "pair",
    "roll", "kit", "test",
]


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        # No "code" — assigned automatically at save, like document numbers.
        fields = [
            "name", "category", "is_batch_tracked", "has_expiry",
            "vat_exempt", "base_unit", "generic_name", "dosage_form", "strength",
            "pack_description", "maintained_price", "pricing_mode",
            "auto_margin_pct", "min_margin_pct", "reorder_level", "shelf_bin",
            "is_active",
        ]
        widgets = {
            "base_unit": forms.TextInput(attrs={
                "list": "unit-options", "placeholder": _("pick or type, e.g. tablet"),
            }),
            "name": forms.TextInput(attrs={
                "placeholder": _("e.g. Paracetamol 500mg tablets"),
            }),
            "generic_name": forms.TextInput(attrs={"placeholder": _("e.g. paracetamol")}),
            "dosage_form": forms.TextInput(attrs={"placeholder": _("e.g. tablet, syrup, injection")}),
            "strength": forms.TextInput(attrs={"placeholder": _("e.g. 500 mg")}),
            "pack_description": forms.TextInput(attrs={
                "placeholder": _("e.g. strip of 10, box of 100"),
            }),
            "shelf_bin": forms.TextInput(attrs={"placeholder": _("e.g. shelf A3")}),
            "reorder_level": forms.NumberInput(attrs={
                "placeholder": _("alert when stock falls below…"),
            }),
        }

    def __init__(self, *args, is_owner: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        if not is_owner:
            for name in OWNER_ONLY_ITEM_FIELDS:
                del self.fields[name]

    def clean(self):
        data = super().clean()
        if data.get("has_expiry") and not data.get("is_batch_tracked"):
            self.add_error(
                "has_expiry",
                _("Expiry dates live on batches — enable batch tracking or clear this."),
            )
        if data.get("pricing_mode") == Item.PricingMode.AUTO and not data.get("auto_margin_pct"):
            self.add_error("auto_margin_pct", _("Required when pricing is automatic."))
        return data


ItemUnitFormSet = inlineformset_factory(
    Item, ItemUnit, fields=["unit_label", "factor_to_base"], extra=1, can_delete=True,
    widgets={"unit_label": forms.TextInput(attrs={"list": "unit-options"})},
)


PARTY_PLACEHOLDERS = {
    "tin": forms.TextInput(attrs={"placeholder": _("10-digit TIN, e.g. 0012345678")}),
    "phone": forms.TextInput(attrs={"placeholder": _("e.g. 0914 123 456")}),
    "address": forms.TextInput(attrs={"placeholder": _("city / subcity / street")}),
}


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            "name", "tin", "license_no", "phone", "mobile", "address", "city",
            "credit_limit", "credit_action", "is_withholding_agent", "is_active",
        ]
        widgets = {
            **PARTY_PLACEHOLDERS,
            "name": forms.TextInput(attrs={"placeholder": _("e.g. Mekelle Clinic")}),
            "license_no": forms.TextInput(attrs={
                "placeholder": _("trade/pharmacy license, e.g. PH-MK-0042"),
            }),
            "mobile": forms.TextInput(attrs={"placeholder": _("e.g. 0912 345 678")}),
            "city": forms.TextInput(attrs={"placeholder": _("e.g. Mekelle")}),
            "credit_limit": forms.NumberInput(attrs={
                "placeholder": _("blank = company default"),
            }),
        }


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ["name", "tin", "phone", "address", "is_active"]
        widgets = {
            **PARTY_PLACEHOLDERS,
            "name": forms.TextInput(attrs={"placeholder": _("e.g. Addis Pharma Import")}),
        }


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ["name", "type", "is_active"]


class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ["name", "is_active"]


class FixedAssetForm(forms.ModelForm):
    class Meta:
        model = FixedAsset
        fields = ["name", "cost", "purchase_date", "useful_life_years", "notes"]
        widgets = {
            "purchase_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class CsvImportForm(forms.Form):
    file = forms.FileField(label=_("CSV file"))
