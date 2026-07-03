from django import forms

from core.models import CompanySettings


class CompanySettingsForm(forms.ModelForm):
    class Meta:
        model = CompanySettings
        fields = CompanySettings.AUDITED_FIELDS
