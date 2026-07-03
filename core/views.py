from functools import wraps
from decimal import Decimal
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from catalog.models import Item
from core.audit import log_change, log_event, snapshot
from core.ethiopian_calendar import format_ethiopian
from core.forms import CompanySettingsForm, UserForm
from core.models import AuditLog, CompanySettings, User
from docs.checks import ExpiryStatus, expiry_status
from docs.handlers_payments import open_balance
from docs.models import DocType, Document, DocumentLine
from stock.models import CostLot, StockBalance, Zone


USER_AUDITED_FIELDS = ["username", "first_name", "last_name", "email", "role", "is_active"]


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
    settings = CompanySettings.load()
    due_limit = today + timedelta(days=14)
    consignments_due = []
    issues = (
        Document.objects.filter(
            doc_type__in=[DocType.CONSIGNMENT_ISSUE, DocType.OPENING_CONSIGNMENT],
            status=Document.Status.POSTED,
            due_date__isnull=False,
            due_date__lte=due_limit,
        )
        .select_related("customer")
        .prefetch_related("lines")
        .order_by("due_date", "pk")
    )
    for issue in issues:
        issued = sum(line.qty_base for line in issue.lines.all())
        settled = 0
        rows = DocumentLine.objects.filter(
            document__related_document=issue,
            document__doc_type=DocType.CONSIGNMENT_SETTLEMENT,
            document__status=Document.Status.POSTED,
        )
        for row in rows:
            settled += row.qty_sold + row.qty_returned + row.qty_expired_unfit
        if issued <= settled:
            continue
        if issue.due_date < today:
            state = _("Overdue")
        elif issue.due_date <= today + timedelta(days=7):
            state = _("Due within 7 days")
        else:
            state = _("Due within 14 days")
        consignments_due.append({"doc": issue, "remaining": issued - settled, "state": state})

    low_stock = []
    for item in Item.objects.filter(reorder_level__isnull=False):
        qty = sum(
            balance.qty for balance in
            StockBalance.objects.filter(item=item, zone=Zone.WAREHOUSE)
        )
        if qty <= item.reorder_level:
            low_stock.append({"item": item, "qty": qty})

    expiry_alerts = []
    balances = (
        StockBalance.objects.filter(qty__gt=0, batch__expiry_date__isnull=False)
        .select_related("item", "batch")
        .order_by("batch__expiry_date", "item__code")[:20]
    )
    for balance in balances:
        status = expiry_status(balance.batch.expiry_date, today, settings.near_expiry_months)
        if status != ExpiryStatus.OK:
            expiry_alerts.append({"balance": balance, "status": status})

    fiscal_mismatches = [
        doc for doc in Document.objects.filter(
            status=Document.Status.POSTED, machine_total__isnull=False,
        ).order_by("-document_date")[:20]
        if doc.machine_total != doc.grand_total
    ]

    ar_overdue = []
    targets = Document.objects.filter(
        doc_type__in=[DocType.SALE, DocType.CONSIGNMENT_SETTLEMENT, DocType.OPENING_AR],
        status=Document.Status.POSTED,
        due_date__lt=today,
    ).select_related("customer").order_by("due_date", "pk")
    for doc in targets:
        if doc.doc_type in (DocType.SALE, DocType.CONSIGNMENT_SETTLEMENT) \
                and doc.sale_kind != Document.SaleKind.CREDIT:
            continue
        balance = open_balance(doc)
        if balance > 0:
            ar_overdue.append({"doc": doc, "balance": balance})

    low_margin = []
    if request.user.is_owner:
        seen = set()
        for lot in CostLot.objects.select_related("item").order_by("-received_at", "-pk"):
            item = lot.item
            if item.pk in seen or item.min_margin_pct is None or item.maintained_price <= 0:
                continue
            seen.add(item.pk)
            margin = (item.maintained_price - lot.unit_cost) * Decimal("100") / item.maintained_price
            if margin < item.min_margin_pct:
                low_margin.append({"item": item, "margin": margin, "cost": lot.unit_cost})
    return render(
        request,
        "core/dashboard.html",
        {
            "today": today,
            "today_ethiopian": format_ethiopian(today),
            "low_stock": low_stock[:10],
            "expiry_alerts": expiry_alerts[:10],
            "consignments_due": consignments_due,
            "fiscal_mismatches": fiscal_mismatches[:10],
            "ar_overdue": ar_overdue[:10],
            "low_margin": low_margin[:10],
        },
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


@owner_required
def user_list(request):
    rows = User.objects.order_by("username")
    return render(request, "core/user_list.html", {"rows": rows})


@owner_required
def user_create(request):
    return _user_form(request, User(), _("Create user"), "USER_CREATE")


@owner_required
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    return _user_form(request, user, _("Edit user"), "USER_UPDATE")


def _user_form(request, user, title, action):
    before = snapshot(user, USER_AUDITED_FIELDS) if user.pk else {}
    if request.method == "POST":
        form = UserForm(request.POST, instance=user)
        if form.is_valid():
            password_changed = bool(form.cleaned_data.get("password"))
            saved = form.save()
            after = snapshot(saved, USER_AUDITED_FIELDS)
            log_change(request.user, action, "User", saved.pk, before, after)
            if password_changed:
                log_event(request.user, "USER_PASSWORD_RESET", "User", saved.pk)
            messages.success(request, _("User saved."))
            return redirect("user_list")
    else:
        form = UserForm(instance=user)
    return render(request, "core/user_form.html", {"form": form, "title": title, "target": user})


@owner_required
def audit_log(request):
    rows = AuditLog.objects.select_related("actor")[:200]
    return render(request, "core/audit_log.html", {"rows": rows})
