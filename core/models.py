"""Core models — spec §3.1: users/roles, settings singleton, audit, sequences."""

from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
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
    # D137: the filters this person last chose, per screen. Not on the session,
    # because D131 means they log in fresh every morning and a session memory
    # would reset daily — which is the complaint. Screen preferences only:
    # nothing here is audited, and nothing here affects money or stock.
    filter_state = models.JSONField(default=dict, blank=True)

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

    class NegativeBalance(models.TextChoices):  # D101
        ALLOW = "ALLOW", _("Allowed — flagged on the Finance page")
        BLOCK_VOID = "BLOCK_VOID", _("Not when voiding")
        BLOCK_POSTING = "BLOCK_POSTING", _("Never — refuse the posting")

    class PrintLayout(models.TextChoices):
        COMPACT = "COMPACT", _("Compact")
        DETAILED = "DETAILED", _("Detailed")
        SALES_ATTACHMENT = "SALES_ATT", _("Cash sales attachment")

    FISCAL_MONTH_CHOICES = [(i + 1, name) for i, name in enumerate(MONTHS[:12])]

    name = models.CharField(_("Company name"), max_length=200, blank=True)
    address = models.CharField(_("Address"), max_length=300, blank=True)
    tin = models.CharField(_("TIN"), max_length=30, blank=True)
    phone = models.CharField(_("Phone numbers"), max_length=100, blank=True,
                             help_text=_("Shown on printed documents."))

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

    # D89: what this business actually uses. Each flag only hides a box on
    # the entry forms — the underlying columns keep working, so posted
    # documents that already carry a discount, a machine total or a pack
    # factor still show and total exactly as before.
    fiscal_machine_present = models.BooleanField(
        _("Fiscal machine present"), default=True,
        help_text=_("Off hides the machine-total box on sales."),
    )
    discounts_enabled = models.BooleanField(
        _("Discounts in use"), default=True,
        help_text=_("Off hides both the document and line discount boxes."),
    )
    unit_conversion_enabled = models.BooleanField(
        _("Pack conversion (factor) in use"), default=True,
        help_text=_("Off hides the factor box; every line counts in base units."),
    )
    sale_price_editable = models.BooleanField(
        _("Sale price editable at the time of sale"), default=False,
        # Reverses D80 (the CN-000002 lesson). The reason it defaults to off
        # is that a typed price silently undercuts the item's maintained
        # price with no record of why. That rationale belongs here, in the
        # code — the help text below is for the person using the app.
        help_text=_(
            "On lets staff type a price on sales, proformas and consignment "
            "issues instead of using the item's price. A discount is the "
            "safer way to charge less: it leaves a record of the reduction."
        ),
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
        _("Print layout"), max_length=9, choices=PrintLayout.choices,
        default=PrintLayout.COMPACT,
    )

    # D101: stock can never go negative (D4, enforced by a DB constraint).
    # Money had no equivalent, so an expense could be paid from an empty
    # drawer and a void could take an account below zero. Whether that is a
    # bug or a fact of life is the owner's call, not ours — a business that
    # does not run every birr through the books has real payments with no
    # recorded income behind them, and refusing those stops real work.
    # Default is today's behaviour, per the D89 rule that a new switch
    # changes nothing until it is flipped.
    negative_balance_policy = models.CharField(
        _("Cash and bank may go negative"), max_length=14,
        choices=NegativeBalance.choices, default=NegativeBalance.ALLOW,
        help_text=_(
            "What happens when a payment would take an account below zero. "
            "Allowed: it goes through and the account shows red on the "
            "Finance page — usually it means income or an opening balance "
            "was never entered. Not when voiding: staff are never stopped, "
            "but voiding an old document may not overdraw an account. "
            "Never: any payment larger than the balance is refused."
        ),
    )

    books_closed_through = models.DateField(  # R71
        _("Books closed through"), null=True, blank=True,
        help_text=_(
            "Leave empty until you start closing months. Once set, documents "
            "dated on or before this day can no longer be voided or "
            "corrected — a void reverses the money today but removes the "
            "document from the month it was in, so a report you have already "
            "printed and filed would quietly change. Move the date forward "
            "each time you finish a month."
        ),
    )

    # D147: the backup runs on Windows under Task Scheduler, not in this
    # container, so these four are carried across in a file the script reads
    # from the mounted backup folder. Nothing here changes what Compose mounts
    # — that stays in .env, because an app that rewrites its own deployment is
    # how a boot loop starts.
    backup_primary_path = models.CharField(
        _("Primary backup folder"), max_length=300, blank=True,
        help_text=_("Where finished backups are kept. Blank = the folder the "
                    "deployment already uses. Full path, e.g. D:\\NarcosBackups."),
    )
    backup_secondary_path = models.CharField(
        _("Second copy folder"), max_length=300, blank=True,
        help_text=_("A second copy, on another drive or a USB stick. Blank = "
                    "none. If the drive is missing the backup still succeeds "
                    "and the run warns."),
    )
    backup_interval_days = models.PositiveSmallIntegerField(
        _("Back up every (days)"), default=1,
        validators=[MinValueValidator(1), MaxValueValidator(30)],
        help_text=_("1 = every day, which is the recommendation. Higher means "
                    "fewer backups and more work at risk. Backing up more than "
                    "once a day needs the Windows task changed on the PC."),
    )
    backup_keep_count = models.PositiveSmallIntegerField(
        _("Nightly backups kept"), default=14,
        validators=[MinValueValidator(7), MaxValueValidator(365)],
        help_text=_("Older ones are removed, except the newest of each month, "
                    "which is kept for a year. The newest good backup is never "
                    "removed."),
    )

    AUDITED_FIELDS = [
        "name", "address", "tin", "phone", "tax_regime", "vat_rate", "tot_rate",
        "prices_tax_exclusive", "withholding_on_sales", "withholding_on_purchases",
        "withholding_rate",
        "fiscal_machine_present", "discounts_enabled", "unit_conversion_enabled",
        "sale_price_editable",
        "near_expiry_months", "consignment_term_months",
        "default_credit_limit", "default_credit_action",
        "fiscal_year_start_month", "date_display", "print_layout",
        "negative_balance_policy", "books_closed_through",
        "backup_primary_path", "backup_secondary_path",
        "backup_interval_days", "backup_keep_count",
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
