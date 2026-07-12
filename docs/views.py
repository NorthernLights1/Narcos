from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from catalog.forms import COMMON_UNITS
from core.audit import log_change, snapshot
from core.models import CompanySettings
from docs.forms import (
    DOC_CONFIG,
    IMPLEMENTED_DOC_TYPES,
    DocumentForm,
    DocumentReferenceForm,
    formsets_for,
)
from docs.handlers_sales import outstanding_by_item_batch
from docs.models import POST_EDITABLE_FIELDS, DocType, Document, DocumentCharge, DocumentLine
from docs.posting import PostingError, post, void
from docs.preview import draft_expected_totals
from stock.models import StockBalance, Zone


def _config(doc_type: str):
    if doc_type not in DOC_CONFIG:
        raise Http404
    return DOC_CONFIG[doc_type]


@login_required
def document_list(request):
    rows = Document.objects.select_related("customer", "supplier").order_by("-created_at")
    doc_type = request.GET.get("type", "")
    status = request.GET.get("status", "")
    query = request.GET.get("q", "").strip()
    if doc_type:
        rows = rows.filter(doc_type=doc_type)
    if status:
        rows = rows.filter(status=status)
    if query:
        rows = rows.filter(
            Q(doc_no__icontains=query)
            | Q(customer__name__icontains=query)
            | Q(supplier__name__icontains=query)
            | Q(payee__icontains=query)
        )
    return render(request, "docs/list.html", {
        "rows": rows[:200],
        "doc_types": [(t, DOC_CONFIG[t]["title"]) for t in IMPLEMENTED_DOC_TYPES],
        "statuses": Document.Status.choices,
        "selected_type": doc_type,
        "selected_status": status,
        "query": query,
    })


@login_required
def document_create(request, doc_type):
    _config(doc_type)
    if doc_type == DocType.STOCK_COUNT and request.method == "GET":
        return _start_stock_count(request)
    if (doc_type == DocType.CONSIGNMENT_SETTLEMENT and request.method == "GET"
            and request.GET.get("from")):
        return _start_consignment_settlement(request, request.GET["from"])
    doc = Document(doc_type=doc_type, created_by=request.user)
    return _draft_form(request, doc)


def _start_consignment_settlement(request, issue_pk):
    """Settle button on a posted issue: prefill one line per item+batch still
    out, so staff only type the sold/returned/expired split (D6)."""
    issue = get_object_or_404(
        Document, pk=issue_pk, status=Document.Status.POSTED,
        doc_type__in=[DocType.CONSIGNMENT_ISSUE, DocType.OPENING_CONSIGNMENT],
    )
    outstanding = outstanding_by_item_batch(issue)
    if not outstanding:
        messages.info(request, _("Nothing is still out on %(no)s — it is fully settled.")
                      % {"no": issue.doc_no})
        return redirect("document_detail", pk=issue.pk)
    with transaction.atomic():
        doc = Document.objects.create(
            doc_type=DocType.CONSIGNMENT_SETTLEMENT, created_by=request.user,
            customer=issue.customer, related_document=issue,
            customer_will_withhold=issue.customer_will_withhold,  # D70
        )
        for group in outstanding:
            DocumentLine.objects.create(
                document=doc,
                item=group["item"],
                batch=group["batch"],
                unit_label=group["item"].base_unit,
                factor=1,
                qty_entered=group["outstanding"],
                qty_base=group["outstanding"],
            )
    messages.success(request, _(
        "Settlement draft for %(no)s — enter how much was sold, returned, or "
        "expired/damaged per line.") % {"no": issue.doc_no})
    return redirect("document_edit", pk=doc.pk)


def _start_stock_count(request):
    with transaction.atomic():
        doc = Document.objects.create(doc_type=DocType.STOCK_COUNT, created_by=request.user)
        balances = (
            StockBalance.objects.filter(zone=Zone.WAREHOUSE, qty__gt=0)
            .select_related("item", "batch", "lot")
            .order_by("item__code", "batch_id", "lot_id")
        )
        for balance in balances:
            DocumentLine.objects.create(
                document=doc,
                item=balance.item,
                batch=balance.batch,
                lot=balance.lot,
                unit_label=balance.item.base_unit,
                factor=1,
                qty_entered=balance.qty,
                qty_base=balance.qty,
                source_zone=Zone.WAREHOUSE,
                target_zone=Zone.WAREHOUSE,
            )
    messages.success(request, _("Stock count snapshot started."))
    return redirect("document_edit", pk=doc.pk)


@login_required
def document_edit(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    if doc.status == Document.Status.POSTED:
        return _reference_form(request, doc)
    if doc.status != Document.Status.DRAFT:
        messages.error(request, _("Voided documents are immutable."))
        return redirect("document_detail", pk=doc.pk)
    return _draft_form(request, doc)


def _totals_preview_context(config, doc: Document) -> dict | None:
    """Client-side preview data for priced documents. Display only — the
    posting handlers recompute everything through docs/tax.py (D32)."""
    if config.get("allocations"):
        # RC/PV: live "paid vs allocated" check mirroring D44
        return {"mode": "payment", "regime": "NONE", "rate": 0,
                "wht_rate": 0, "wht_enabled": "0"}
    if doc.doc_type == DocType.CONSIGNMENT_SETTLEMENT:
        if not doc.related_document_id:
            return None  # blank-form path: prices unknown until posting
        settings = CompanySettings.load()
        rate = doc.related_document.tax_rate_snapshot
        return {
            "mode": "settlement",
            "regime": "VAT" if rate else "NONE",  # rate frozen on the issue
            "rate": rate,
            "wht_rate": settings.withholding_rate,
            "wht_enabled": "1" if settings.withholding_on_sales else "0",
            "will_withhold": "1" if doc.customer_will_withhold else "0",  # D70
        }
    lines = config.get("lines", ())
    if ("unit_cost_entered" in lines and "qty_entered" in lines
            and "unit_price" not in lines):
        # Receiving-style (GRN, opening stock): Σ qty × unit cost, no tax (D63)
        return {"mode": "cost", "regime": "NONE", "rate": 0,
                "wht_rate": 0, "wht_enabled": "0"}
    if "unit_price" not in config.get("lines", ()):
        return None
    settings = CompanySettings.load()
    rate = {
        CompanySettings.TaxRegime.VAT: settings.vat_rate,
        CompanySettings.TaxRegime.TOT: settings.tot_rate,
    }.get(settings.tax_regime, 0)
    return {
        "mode": "price",
        "regime": settings.tax_regime,
        "rate": rate,
        "wht_rate": settings.withholding_rate,
        "wht_enabled": "1" if settings.withholding_on_sales else "0",
    }


def _draft_form(request, doc: Document):
    config = _config(doc.doc_type)
    if request.method == "POST":
        form = DocumentForm(request.POST, instance=doc, doc_type=doc.doc_type)
        formsets = formsets_for(doc, request.POST)
        if form.is_valid() and all(formset.is_valid() for _prefix, _title, formset in formsets):
            with transaction.atomic():
                saved = form.save(commit=False)
                saved.doc_type = doc.doc_type
                if saved.created_by_id is None:
                    saved.created_by = request.user
                saved.save()
                for _prefix, _title, formset in formsets:
                    formset.instance = saved
                    formset.save()
            messages.success(request, _("Draft saved."))
            return redirect("document_detail", pk=saved.pk)
    else:
        form = DocumentForm(instance=doc, doc_type=doc.doc_type)
        formsets = formsets_for(doc)
    return render(request, "docs/form.html", {
        "doc": doc,
        "title": config["title"],
        "form": form,
        "formsets": formsets,
        "totals_preview": _totals_preview_context(config, doc),
        "common_units": COMMON_UNITS,
    })


def _reference_form(request, doc: Document):
    fields = sorted(POST_EDITABLE_FIELDS)
    if request.method == "POST":
        before = snapshot(doc, fields)
        form = DocumentReferenceForm(request.POST, instance=doc)
        if form.is_valid():
            saved = form.save()
            after = snapshot(saved, fields)
            log_change(
                actor=request.user,
                action="DOCUMENT_REFERENCE_UPDATE",
                entity="Document",
                entity_id=saved.pk,
                before=before,
                after=after,
            )
            messages.success(request, _("Reference fields saved."))
            return redirect("document_detail", pk=saved.pk)
    else:
        form = DocumentReferenceForm(instance=doc)
    return render(request, "docs/form.html", {
        "doc": doc,
        "title": _("Reference fields"),
        "form": form,
        "formsets": [],
    })


@login_required
def document_detail(request, pk):
    doc = get_object_or_404(
        Document.objects.select_related(
            "customer", "supplier", "created_by", "posted_by", "voided_by",
        ),
        pk=pk,
    )
    return render(request, "docs/detail.html", {
        "doc": doc,
        "config": DOC_CONFIG.get(doc.doc_type),
        "expected": draft_expected_totals(doc),
    })


@login_required
def document_print(request, pk):
    doc = get_object_or_404(
        Document.objects.filter(status=Document.Status.POSTED)
        .select_related("customer", "supplier", "created_by", "posted_by")
        .prefetch_related("lines__item", "lines__batch", "charges", "payment_lines__account"),
        pk=pk,
    )
    settings = CompanySettings.load()
    layout = request.GET.get("layout") or settings.print_layout
    if layout not in CompanySettings.PrintLayout.values:
        layout = settings.print_layout
    return render(request, "docs/print.html", {
        "company": settings,
        "doc": doc,
        "layout": layout,
    })


@login_required
def withholding_certificate_print(request, pk):
    doc = get_object_or_404(
        Document.objects.filter(
            doc_type=DocType.SUPPLIER_PAYMENT,
            status=Document.Status.POSTED,
            withheld_amount__gt=0,
        ).select_related("supplier"),
        pk=pk,
    )
    return render(request, "docs/wht_certificate.html", {
        "company": CompanySettings.load(),
        "doc": doc,
    })


@login_required
@require_POST
def document_convert_sale(request, pk):
    source = get_object_or_404(
        Document.objects.filter(doc_type=DocType.PROFORMA, status=Document.Status.POSTED)
        .prefetch_related("lines", "charges"),
        pk=pk,
    )
    with transaction.atomic():
        sale = Document.objects.create(
            doc_type=DocType.SALE,
            created_by=request.user,
            customer=source.customer,
            doc_discount=source.doc_discount,
            notes=_("Converted from %(no)s") % {"no": source.doc_no},
        )
        for line in source.lines.all():
            DocumentLine.objects.create(
                document=sale, item=line.item, batch=line.batch,
                unit_label=line.unit_label, factor=line.factor,
                qty_entered=line.qty_entered, unit_price=line.unit_price,
                line_discount=line.line_discount,
            )
        for charge in source.charges.all():
            DocumentCharge.objects.create(
                document=sale, label=charge.label, amount=charge.amount,
                is_taxable=charge.is_taxable,
            )
    messages.success(request, _("Draft sale created."))
    return redirect("document_edit", pk=sale.pk)


@login_required
@require_POST
def document_post(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    try:
        posted = post(doc, request.user, request.POST.get("override_reason", ""))
    except PostingError as exc:
        messages.error(request, str(exc))
        return redirect("document_detail", pk=doc.pk)
    messages.success(request, _("Posted %(no)s.") % {"no": posted.doc_no})
    return redirect("document_detail", pk=posted.pk)


@login_required
@require_POST
def document_void(request, pk):
    if not request.user.is_owner:
        raise PermissionDenied
    doc = get_object_or_404(Document, pk=pk)
    try:
        voided = void(doc, request.user, request.POST.get("reason", ""))
    except PostingError as exc:
        messages.error(request, str(exc))
        return redirect("document_detail", pk=doc.pk)
    messages.success(request, _("Voided %(no)s.") % {"no": voided.doc_no})
    return redirect("document_detail", pk=voided.pk)


@login_required
@require_POST
def document_delete(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    if doc.status != Document.Status.DRAFT:
        messages.error(request, _("Only drafts can be deleted."))
        return redirect("document_detail", pk=doc.pk)
    doc.delete()
    messages.success(request, _("Draft deleted."))
    return redirect("document_list")
