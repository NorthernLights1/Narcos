from django import forms
from django.utils.translation import gettext_lazy as _

from core.models import CompanySettings, User


class CompanySettingsForm(forms.ModelForm):
    """Settings, grouped. Twenty-three fields in one flat grid meant the rule
    you wanted was findable only by reading all of them top to bottom."""

    GROUPS = [
        (_("Company"), ["name", "address", "tin", "phone"]),
        (_("Tax"), ["tax_regime", "vat_rate", "tot_rate", "prices_tax_exclusive",
                    "withholding_on_sales", "withholding_on_purchases",
                    "withholding_rate"]),
        (_("What this business uses"), ["fiscal_machine_present",
                                        "discounts_enabled",
                                        "sale_price_editable"]),
        (_("Money rules"), ["negative_balance_policy", "default_credit_limit",
                            "default_credit_action"]),
        (_("Stock"), ["near_expiry_months", "consignment_term_months"]),
        (_("Dates and printing"), ["fiscal_year_start_month", "date_display",
                                   "print_layout"]),
    ]

    class Meta:
        model = CompanySettings
        fields = CompanySettings.AUDITED_FIELDS

    def grouped(self):
        """Yield (title, [bound fields]). A field nobody listed still appears,
        under Other — a new setting must never go invisible just because it
        was left out of a group."""
        placed = set()
        for title, names in self.GROUPS:
            fields = [self[name] for name in names if name in self.fields]
            placed.update(field.name for field in fields)
            if fields:
                yield title, fields
        leftover = [self[name] for name in self.fields if name not in placed]
        if leftover:
            yield _("Other"), leftover


class UserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, required=False)

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role", "is_active", "password"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk is None:
            self.fields["password"].required = True

    def clean_password(self):
        password = self.cleaned_data.get("password", "")
        if password and len(password) < 8:
            raise forms.ValidationError(_("Password must be at least 8 characters."))
        return password

    def save(self, commit=True):
        password = self.cleaned_data.pop("password", "")
        user = super().save(commit=False)
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user
