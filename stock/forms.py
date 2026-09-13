"""Batch corrections (D121). The one field the app lets anybody change on a
batch that documents already reference — and only the owner, with a reason."""

from django import forms
from django.utils.translation import gettext_lazy as _

from stock.models import Batch


class BatchExpiryForm(forms.ModelForm):
    """R62/D121: correct a mistyped expiry without voiding.

    The reason is mandatory because this is not an ordinary field edit. The
    date is read by every expiry rule there is (D46 blocks selling expired
    stock, D59 warns on near expiry, D61 orders picking first-expired-first)
    and one batch number is shared by every document that ever received it,
    so the change lands on all of them at once. The audit row has to say why.
    """

    reason = forms.CharField(
        label=_("Reason"),
        max_length=200,
        widget=forms.TextInput(attrs={
            "placeholder": _("e.g. read 2026 off the carton, it says 2029"),
        }),
        help_text=_("Kept in the audit log beside the old and new dates."),
    )

    class Meta:
        model = Batch
        fields = ["expiry_date"]
        widgets = {"expiry_date": forms.DateInput(attrs={"type": "date"})}
        labels = {"expiry_date": _("Corrected expiry")}

    def clean_expiry_date(self):
        expiry = self.cleaned_data.get("expiry_date")
        if expiry is None:
            raise forms.ValidationError(_("An expiry date is required."))
        return expiry

    def clean_reason(self):
        reason = self.cleaned_data["reason"].strip()
        if len(reason) < 4:
            raise forms.ValidationError(_("Say why, in a few words."))
        return reason
