from django import forms
from django.utils.translation import gettext_lazy as _

from core.models import CompanySettings, User


class CompanySettingsForm(forms.ModelForm):
    class Meta:
        model = CompanySettings
        fields = CompanySettings.AUDITED_FIELDS


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
