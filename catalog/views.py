"""Master-data CRUD (audited, D47) + duplicate search (D26) + CSV imports (D57)."""

from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from catalog import importers
from catalog.forms import (
    COMMON_UNITS,
    AccountForm,
    CsvImportForm,
    CustomerForm,
    ExpenseCategoryForm,
    FixedAssetForm,
    ItemForm,
    ItemUnitFormSet,
    SupplierForm,
)
from catalog.models import (
    Account,
    Customer,
    ExpenseCategory,
    FixedAsset,
    Item,
    Supplier,
)
from core.audit import log_change, log_event, snapshot
from core.views import owner_required


@dataclass(frozen=True)
class MasterConfig:
    model: type
    form: type
    title: str
    columns: list[str]  # list-page columns (field names)
    search_fields: list[str]  # D26 duplicate search


MASTER: dict[str, MasterConfig] = {
    "items": MasterConfig(Item, ItemForm, gettext_lazy("Items"),
                          ["code", "name", "category", "base_unit", "maintained_price", "is_active"],
                          ["code", "name", "generic_name"]),
    "customers": MasterConfig(Customer, CustomerForm, gettext_lazy("Customers"),
                              ["code", "name", "phone", "is_withholding_agent", "is_active"],
                              ["code", "name", "tin"]),
    "suppliers": MasterConfig(Supplier, SupplierForm, gettext_lazy("Suppliers"),
                              ["code", "name", "phone", "is_active"],
                              ["code", "name", "tin"]),
    "accounts": MasterConfig(Account, AccountForm, gettext_lazy("Accounts"),
                             ["name", "type", "is_active"], ["name"]),
    "expense-categories": MasterConfig(ExpenseCategory, ExpenseCategoryForm,
                                       gettext_lazy("Expense categories"),
                                       ["name", "is_active"], ["name"]),
    "fixed-assets": MasterConfig(FixedAsset, FixedAssetForm, gettext_lazy("Fixed assets"),
                                 ["name", "cost", "purchase_date", "useful_life_years"],
                                 ["name"]),
}


def _config(kind: str) -> MasterConfig:
    if kind not in MASTER:
        raise Http404
    return MASTER[kind]


@login_required
def master_list(request, kind):
    cfg = _config(kind)
    query = request.GET.get("q", "").strip()
    rows = cfg.model.objects.all()
    if query:
        filters = Q()
        for field_name in cfg.search_fields:
            filters |= Q(**{f"{field_name}__icontains": query})
        rows = rows.filter(filters)
    return render(request, "catalog/list.html", {
        "cfg": cfg, "kind": kind, "rows": rows[:200], "query": query,
    })


@login_required
def master_form(request, kind, pk=None):
    cfg = _config(kind)
    instance = get_object_or_404(cfg.model, pk=pk) if pk else None
    form_kwargs = {"instance": instance}
    if cfg.form is ItemForm:
        form_kwargs["is_owner"] = request.user.is_owner

    units_formset = None
    if request.method == "POST":
        form = cfg.form(request.POST, **form_kwargs)
        before = snapshot(instance, cfg.model.AUDITED_FIELDS) if instance else {}
        if form.is_valid():
            saved = form.save()
            if cfg.model is Item:
                units_formset = ItemUnitFormSet(request.POST, instance=saved)
                if not units_formset.is_valid():
                    return render(request, "catalog/form.html", {
                        "cfg": cfg, "kind": kind, "form": form,
                        "units_formset": units_formset, "instance": instance,
                        "common_units": COMMON_UNITS,
                    })
                units_formset.save()
            after = snapshot(saved, cfg.model.AUDITED_FIELDS)
            log_change(
                actor=request.user,
                action="MASTER_UPDATE" if instance else "MASTER_CREATE",
                entity=cfg.model.__name__,
                entity_id=saved.pk,
                before=before,
                after=after,
            )
            messages.success(request, _("Saved."))
            return redirect("master_list", kind=kind)
    else:
        form = cfg.form(**form_kwargs)
    if cfg.model is Item and units_formset is None:
        units_formset = ItemUnitFormSet(instance=instance)
    return render(request, "catalog/form.html", {
        "cfg": cfg, "kind": kind, "form": form,
        "units_formset": units_formset, "instance": instance,
        "common_units": COMMON_UNITS if cfg.model is Item else None,
    })


@login_required
def master_search(request, kind):
    """D26: search-as-you-type duplicate check on create forms (HTMX)."""
    cfg = _config(kind)
    query = (
        request.GET.get("q") or request.GET.get("code") or request.GET.get("name") or ""
    ).strip()
    rows = []
    if len(query) >= 2:
        filters = Q()
        for field_name in cfg.search_fields:
            filters |= Q(**{f"{field_name}__icontains": query})
        rows = cfg.model.objects.filter(filters)[:8]
    return render(request, "catalog/_matches.html", {"rows": rows})


IMPORTERS = {
    "items": (importers.import_items, gettext_lazy("Items")),
    "customers": (importers.import_customers, gettext_lazy("Customers")),
    "suppliers": (importers.import_suppliers, gettext_lazy("Suppliers")),
    "opening-stock": (importers.import_opening_stock, gettext_lazy("Opening stock")),
    "opening-ar": (importers.import_opening_ar, gettext_lazy("Opening receivable")),
    "opening-ap": (importers.import_opening_ap, gettext_lazy("Opening payable")),
    "opening-cash": (importers.import_opening_cash, gettext_lazy("Opening cash")),
}


@owner_required
def csv_import(request, kind):
    if kind not in IMPORTERS:
        raise Http404
    importer, title = IMPORTERS[kind]
    result = None
    if request.method == "POST":
        form = CsvImportForm(request.POST, request.FILES)
        if form.is_valid():
            if kind in MASTER:
                result = importer(form.cleaned_data["file"])
            else:
                result = importer(form.cleaned_data["file"], request.user)
            if result.is_clean:
                log_event(
                    actor=request.user, action="CSV_IMPORT", entity=kind,
                    detail={"created": result.created},
                )
                messages.success(
                    request,
                    _("Imported %(n)d records.") % {"n": result.created},
                )
                if kind in MASTER:
                    return redirect("master_list", kind=kind)
                return redirect("document_list")
    else:
        form = CsvImportForm()
    return render(request, "catalog/import.html", {
        "form": form, "title": title, "kind": kind, "result": result,
        "back_url": "master_list" if kind in MASTER else "document_list",
    })
