"""Core models — spec §3.1: users/roles, settings singleton, audit, sequences."""

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.ethiopian_calendar import MONTHS


class User(AbstractUser):
    """D33/D42: two roles. Owner approves/voids/overrides; employee does daily work."""

    class Role(models.TextChoices):
        OWNER = "OWNER", _("Owner")
        EMPLOYEE = "EMPLOYEE", _("Employee")

    role = models.CharField(
        max_length=10, choices=Role.choices, default=Role.EMPLOYEE
    )

    @property
    def is_owner(self) -> bool:
        return self.role == self.Role.OWNER


class CompanySettings(models.Model):
    """Singleton (§3.1). Every change is audited (D47) — see SettingsView."""

    class TaxRegime(models.TextChoices):
        VAT = "VAT", _("VAT")
        TOT = "TOT", _("TOT (turnover tax)")
        NONE = "NONE", _("None")

    class CreditAction(models.TextChoices):
        WARN = "WARN", _("Warn and allow")
        BLOCK = "BLOCK", _("Block (owner may override)")

    class DateDisplay(models.TextChoices):
        GREGORIAN = "GREGORIAN", _("Gregorian")
        ETHIOPIAN = "ETHIOPIAN", _("Ethiopian")
        BOTH = "BOTH", _("Both")

    class PrintLayout(models.TextChoices):
        COMPACT = "COMPACT", _("Compact")
        DETAILED = "DETAILED", _("Detailed")

    FISCAL_MONTH_CHOICES = [(i + 1, name) for i, name in enumerate(MONTHS[:12])]

    name = models.CharField(_("Company name"), max_length=200, blank=True)
    address = models.CharField(_("Address"), max_length=300, blank=True)
    tin = models.CharField(_("TIN"), max_length=30, blank=True)

    tax_regime = models.CharField(  # D7
        _("Tax regime"), max_length=4, choices=TaxRegime.choices, default=TaxRegime.VAT
    )
    vat_rate = models.DecimalField(_("VAT rate %"), max_digits=5, decimal_places=2, default=15)
    tot_rate = models.DecimalField(_("TOT rate %"), max_digits=5, decimal_places=2, default=2)
    prices_tax_exclusive = models.BooleanField(_("Prices entered tax-exclusive"), default=True)  # D31

    withholding_on_sales = models.BooleanField(_("Withholding on sales"), default=False)  # D51
    withholding_on_purchases = models.BooleanField(_("Withholding on purchases"), default=False)  # D52
    withholding_rate = models.DecimalField(
        _("Withholding rate %"), max_digits=5, decimal_places=2, default=3
    )

    near_expiry_months = models.PositiveSmallIntegerField(_("Near-expiry months"), default=6)  # D59
    consignment_term_months = models.PositiveSmallIntegerField(
        _("Consignment term (months)"), default=3
    )  # D60

    default_credit_limit = models.DecimalField(  # D25
        _("Default credit limit"), max_digits=14, decimal_places=2, null=True, blank=True
    )
    default_credit_action = models.CharField(
        _("Default credit action"), max_length=5,
        choices=CreditAction.choices, default=CreditAction.WARN,
    )

    fiscal_year_start_month = models.PositiveSmallIntegerField(  # D19
        _("Fiscal year starts (Ethiopian month)"), choices=FISCAL_MONTH_CHOICES, default=11
    )
    date_display = models.CharField(
        _("Date display"), max_length=10, choices=DateDisplay.choices,
        default=DateDisplay.GREGORIAN,
    )
    print_layout = models.CharField(
        _("Print layout"), max_length=8, choices=PrintLayout.choices,
        default=PrintLayout.COMPACT,
    )

    AUDITED_FIELDS = [
        "name", "address", "tin", "tax_regime", "vat_rate", "tot_rate",
        "prices_tax_exclusive", "withholding_on_sales", "withholding_on_purchases",
        "withholding_rate", "near_expiry_months", "consignment_term_months",
        "default_credit_limit", "default_credit_action",
        "fiscal_year_start_month", "date_display", "print_layout",
    ]

    class Meta:
        verbose_name = _("Company settings")

    def save(self, *args, **kwargs):
        self.pk = 1  # ponytail: hard singleton, one company per install (01 §what-it-is)
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "CompanySettings":
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class AuditLog(models.Model):
    """Append-only (D47). Never updated or deleted by application code."""

    actor = models.ForeignKey(
        "core.User", null=True, on_delete=models.SET_NULL, related_name="audit_entries"
    )
    action = models.CharField(max_length=50)
    entity = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=50, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-at"]

    def delete(self, *args, **kwargs):
        raise NotImplementedError("Audit log entries are never deleted (D47).")

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise NotImplementedError("Audit log entries are never edited (D47).")
        super().save(*args, **kwargs)


class NumberSequence(models.Model):
    """Gapless per-doc-type numbering (D8). take() must run inside the posting
    transaction: select_for_update takes a real row lock on PostgreSQL, so
    two concurrent postings of the same doc type serialize here (D14/D66)."""

    doc_type = models.CharField(max_length=25, unique=True)
    next_no = models.PositiveIntegerField(default=1)

    @classmethod
    def take(cls, doc_type: str) -> int:
        seq, _created = cls.objects.select_for_update().get_or_create(doc_type=doc_type)
        number = seq.next_no
        seq.next_no += 1
        seq.save(update_fields=["next_no"])
        return number
