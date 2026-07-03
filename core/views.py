from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from core.audit import log_change, snapshot
from core.ethiopian_calendar import format_ethiopian
from core.forms import CompanySettingsForm
from core.models import CompanySettings


def owner_required(view):
    """D33: owner-only screens 403 for employees (never a silent redirect)."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_owner:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


@login_required
def dashboard(request):
    today = timezone.localdate()
    return render(
        request,
        "core/dashboard.html",
        {"today": today, "today_ethiopian": format_ethiopian(today)},
    )


@owner_required
def company_settings(request):
    instance = CompanySettings.load()
    if request.method == "POST":
        before = snapshot(instance, CompanySettings.AUDITED_FIELDS)
        form = CompanySettingsForm(request.POST, instance=instance)
        if form.is_valid():
            saved = form.save()
            after = snapshot(saved, CompanySettings.AUDITED_FIELDS)
            log_change(
                actor=request.user,
                action="SETTINGS_UPDATE",
                entity="CompanySettings",
                entity_id=saved.pk,
                before=before,
                after=after,
            )
            messages.success(request, _("Settings saved."))
            return redirect("company_settings")
    else:
        form = CompanySettingsForm(instance=instance)
    return render(request, "core/settings_form.html", {"form": form})
