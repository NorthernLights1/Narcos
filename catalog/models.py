"""Catalog models — spec §3.2: items/units, parties, accounts, categories, assets."""

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

# Master codes are assigned automatically, like document numbers (D8): the
# forms never ask for one. An explicit code still wins when set programmatically
# (CSV migration of a legacy numbering scheme).
MASTER_CODE_PREFIXES = {"Item": "ITM", "Customer": "CUS", "Supplier": "SUP"}


class AutoCodeModel(models.Model):
    """Blank code → next PREFIX-0001 from the same locked per-key sequence
    documents use. Skips numbers already taken by imported legacy codes."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.code:
            from core.models import NumberSequence

            model = type(self)
            prefix = MASTER_CODE_PREFIXES[model.__name__]
            with transaction.atomic():
                while True:
                    number = NumberSequence.take(f"CODE_{model.__name__.upper()}")
                    candidate = f"{prefix}-{number:04d}"
                    if not model.objects.filter(code=candidate).exists():
                        self.code = candidate
                        break
        super().save(*args, **kwargs)


class Item(AutoCodeModel):
    """D29: mixed catalog — drugs, reagents, supplies, equipment."""

    class Category(models.TextChoices):
        DRUG = "DRUG", _("Drug")
        REAGENT = "REAGENT", _("Reagent")
        SUPPLY = "SUPPLY", _("Medical supply")
        EQUIPMENT = "EQUIPMENT", _("Equipment")

    class PricingMode(models.TextChoices):
        MANUAL = "MANUAL", _("Maintained price")
        AUTO = "AUTO", _("Auto: cost + margin %")

    code = models.CharField(_("Code"), max_length=30, unique=True)
    name = models.CharField(_("Name"), max_length=200)
    category = models.CharField(
        _("Category"), max_length=10, choices=Category.choices, default=Category.DRUG
    )
    is_batch_tracked = models.BooleanField(_("Batch tracked"), default=True)  # D29
    has_expiry = models.BooleanField(_("Has expiry"), default=True)  # D22
    vat_exempt = models.BooleanField(  # D30/D50
        _("VAT exempt"), default=False,
        help_text=_("Medicines are VAT-exempt by law — confirm with your accountant."),
    )
    base_unit = models.CharField(  # D62
        _("Base unit"), max_length=50, default="unit",
        help_text=_('The unit stock is counted in, e.g. "pack of 10".'),
    )

    # Drug-only, all optional (D29)
    generic_name = models.CharField(_("Generic name"), max_length=200, blank=True)
    dosage_form = models.CharField(_("Dosage form"), max_length=100, blank=True)
    strength = models.CharField(_("Strength"), max_length=100, blank=True)
    pack_description = models.CharField(_("Pack description"), max_length=200, blank=True)

    # Pricing (D23) — margin fields are owner-only in forms (D33)
    maintained_price = models.DecimalField(
        _("Selling price"), max_digits=14, decimal_places=2, default=0
    )
    pricing_mode = models.CharField(
        _("Pricing mode"), max_length=6, choices=PricingMode.choices,
        default=PricingMode.MANUAL,
    )
    auto_margin_pct = models.DecimalField(
        _("Auto margin %"), max_digits=5, decimal_places=2, null=True, blank=True
    )
    min_margin_pct = models.DecimalField(
        _("Low-margin alert %"), max_digits=5, decimal_places=2, null=True, blank=True
    )

    reorder_level = models.PositiveIntegerField(_("Reorder level"), null=True, blank=True)  # D34
    shelf_bin = models.CharField(_("Shelf/bin"), max_length=50, blank=True)
    is_active = models.BooleanField(_("Active"), default=True)

    AUDITED_FIELDS = [
        "code", "name", "category", "is_batch_tracked", "has_expiry", "vat_exempt",
        "base_unit", "generic_name", "dosage_form", "strength", "pack_description",
        "maintained_price", "pricing_mode", "auto_margin_pct", "min_margin_pct",
        "reorder_level", "shelf_bin", "is_active",
    ]

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class ItemUnit(models.Model):
    """D62: alternate unit with a fixed whole-number factor to the base unit."""

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="units")
    unit_label = models.CharField(_("Unit label"), max_length=50)
    factor_to_base = models.PositiveIntegerField(_("Units of base per 1"))

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["item", "unit_label"], name="uniq_item_unit_label"),
            models.CheckConstraint(
                condition=models.Q(factor_to_base__gt=1), name="unit_factor_gt_1"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.unit_label} ×{self.factor_to_base}"


class Customer(AutoCodeModel):
    class CreditAction(models.TextChoices):  # D25; null on customer = company default
        WARN = "WARN", _("Warn and allow")
        BLOCK = "BLOCK", _("Block (owner may override)")

    code = models.CharField(_("Code"), max_length=30, unique=True)
    name = models.CharField(_("Name"), max_length=200)
    tin = models.CharField(_("TIN"), max_length=30, blank=True)
    license_no = models.CharField(_("License no."), max_length=50, blank=True)
    phone = models.CharField(_("Phone"), max_length=30, blank=True)
    mobile = models.CharField(_("Mobile"), max_length=30, blank=True)
    address = models.CharField(_("Address"), max_length=300, blank=True)
    city = models.CharField(_("City"), max_length=100, blank=True)
    credit_limit = models.DecimalField(
        _("Credit limit"), max_digits=14, decimal_places=2, null=True, blank=True,
        help_text=_("Blank = company default."),
    )
    credit_action = models.CharField(
        _("When over limit"), max_length=5, choices=CreditAction.choices,
        null=True, blank=True, help_text=_("Blank = company default."),
    )
    is_withholding_agent = models.BooleanField(  # D51
        _("Withholding agent"), default=False,
        help_text=_("PLCs, government, NGOs — they keep back the withholding % when paying."),
    )
    is_active = models.BooleanField(_("Active"), default=True)

    AUDITED_FIELDS = [
        "code", "name", "tin", "license_no", "phone", "mobile", "address",
        "city", "credit_limit", "credit_action", "is_withholding_agent",
        "is_active",
    ]

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class Supplier(AutoCodeModel):
    code = models.CharField(_("Code"), max_length=30, unique=True)
    name = models.CharField(_("Name"), max_length=200)
    tin = models.CharField(_("TIN"), max_length=30, blank=True)
    phone = models.CharField(_("Phone"), max_length=30, blank=True)
    address = models.CharField(_("Address"), max_length=300, blank=True)
    is_active = models.BooleanField(_("Active"), default=True)

    AUDITED_FIELDS = ["code", "name", "tin", "phone", "address", "is_active"]

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class Account(models.Model):
    """D9/D10/D11: cash drawers and bank accounts money moves through."""

    class Type(models.TextChoices):
        CASH = "CASH", _("Cash")
        BANK = "BANK", _("Bank")

    name = models.CharField(_("Name"), max_length=100, unique=True)
    type = models.CharField(_("Type"), max_length=4, choices=Type.choices)
    is_active = models.BooleanField(_("Active"), default=True)

    AUDITED_FIELDS = ["name", "type", "is_active"]

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ExpenseCategory(models.Model):
    name = models.CharField(_("Name"), max_length=100, unique=True)
    is_active = models.BooleanField(_("Active"), default=True)

    AUDITED_FIELDS = ["name", "is_active"]

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "expense categories"

    def __str__(self) -> str:
        return self.name


class FixedAsset(models.Model):
    """D16/D49: recording only — no depreciation display in v1."""

    name = models.CharField(_("Name"), max_length=200)
    cost = models.DecimalField(_("Cost"), max_digits=14, decimal_places=2)
    purchase_date = models.DateField(_("Purchase date"))
    useful_life_years = models.PositiveSmallIntegerField(_("Useful life (years)"))
    notes = models.TextField(_("Notes"), blank=True)

    AUDITED_FIELDS = ["name", "cost", "purchase_date", "useful_life_years", "notes"]

    class Meta:
        ordering = ["-purchase_date"]

    def __str__(self) -> str:
        return self.name
