import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import Coalesce
from django.forms import modelform_factory
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from catalog.forms import COMMON_UNITS, ItemForm
from catalog.models import Customer, Supplier
from core.audit import log_change, snapshot
from core.models import CompanySettings
from docs.handlers_payments import AP_TARGET_TYPES, AR_TARGET_TYPES
from docs.forms import (
    DOC_CONFIG,
    IMPLEMENTED_DOC_TYPES,
    DocumentForm,
    fields_hidden_by_settings,
    formsets_for,
)
from docs.handlers_sales import outstanding_by_item_batch
from docs.models import (
    OWNER_ONLY_POST_EDITS,
    POST_EDITABLE_FIELDS,
    POST_EDITABLE_ORDER,
    DocType,
    Document,
    DocumentCharge,
    DocumentLine,
)
from docs.posting import PostingError, get_handler, post, void
from docs.preview import draft_expected_totals
from docs.settlement import (
    SETTLEMENT_FILTERS,
    annotate_settlement,
    filter_settlement,
    settlement_context,
    settlement_state,
)
from money.models import PaymentAllocation, PaymentLine
from stock.models import StockBalance, Zone


def _config(doc_type: str):
    if doc_type not in DOC_CONFIG:
        raise Http404
    return DOC_CONFIG[doc_type]


def _parse_date(value):
    try:
        return dt.date.fromisoformat(value or "")
    except ValueError:
        return None


@login_required
def document_list(request):
    rows = annotate_settlement(
        Document.objects.select_related("customer", "supplier")
    ).annotate(
        attachment_count=Count("attachments",
                               filter=Q(attachments__is_voided=False)),
    ).order_by("-created_at")
    doc_type = request.GET.get("type", "")
    status = request.GET.get("status", "")
    settlement = request.GET.get("settlement", "")
    query = request.GET.get("q", "").strip()
    customer_id = request.GET.get("customer", "")
    supplier_id = request.GET.get("supplier", "")
    start = _parse_date(request.GET.get("start"))
    end = _parse_date(request.GET.get("end"))
    if doc_type:
        rows = rows.filter(doc_type=doc_type)
    if status:
        rows = rows.filter(status=status)
    if settlement:
        rows = filter_settlement(rows, settlement)
    if customer_id.isdigit():
        rows = rows.filter(customer_id=customer_id)
    if supplier_id.isdigit():
        rows = rows.filter(supplier_id=supplier_id)
    if start or end:
        # Drafts have no document_date yet — fall back to creation time so
        # they don't vanish from a date-filtered view.
        rows = rows.annotate(effective_at=Coalesce("document_date", "created_at"))
        if start:
            rows = rows.filter(effective_at__date__gte=start)
        if end:
            rows = rows.filter(effective_at__date__lte=end)
    if query:
        rows = rows.filter(
            Q(doc_no__icontains=query)
            | Q(customer__name__icontains=query)
            | Q(supplier__name__icontains=query)
            | Q(payee__icontains=query)
        )
    return render(request, "docs/list.html", {
        "rows": [(doc, settlement_state(doc)) for doc in rows[:200]],
        "doc_types": [(t, DOC_CONFIG[t]["title"]) for t in IMPLEMENTED_DOC_TYPES],
        "statuses": Document.Status.choices,
        "settlement_filters": SETTLEMENT_FILTERS,
        "customers": Customer.objects.filter(is_active=True).order_by("code"),
        "suppliers": Supplier.objects.filter(is_active=True).order_by("code"),
        "selected_type": doc_type,
        "selected_status": status,
        "selected_settlement": settlement,
        "selected_customer": customer_id,
        "selected_supplier": supplier_id,
        "start": start,
        "end": end,
        "query": query,
    })


@login_required
def document_create(request, doc_type):
    _config(doc_type)
    if doc_type == DocType.STOCK_COUNT and request.method == "GET":
        return _start_stock_count(request)
    if request.method == "GET" and request.GET.get("from"):
        if doc_type == DocType.CONSIGNMENT_SETTLEMENT:
            return _start_consignment_settlement(request, request.GET["from"])
        if doc_type in (DocType.CUSTOMER_PAYMENT, DocType.SUPPLIER_PAYMENT):
            return _start_payment(request, doc_type, request.GET["from"])
    doc = Document(doc_type=doc_type, created_by=request.user)
    return _draft_form(request, doc)


def _start_payment(request, doc_type, target_pk):
    """Record payment / Pay supplier button on a posted invoice (D74): draft
    RC/PV with the party, an allocation at the invoice's open balance, and
    the expected withholding prefilled — staff pick the account and post.
    Display convenience only: the handler re-checks everything under lock."""
    is_customer = doc_type == DocType.CUSTOMER_PAYMENT
    target = get_object_or_404(
        Document, pk=target_pk, status=Document.Status.POSTED,
        doc_type__in=AR_TARGET_TYPES if is_customer else AP_TARGET_TYPES,
    )
    state = settlement_state(target)
    if state is None or state["kind"] != "money" or state["open"] <= 0:
        messages.info(request, _("%(no)s has nothing left to settle.")
                      % {"no": target.doc_no})
        return redirect("document_detail", pk=target.pk)
    settings = CompanySettings.load()
    withholding_enabled = (settings.withholding_on_sales if is_customer
                           else settings.withholding_on_purchases)
    withheld = 0
    if withholding_enabled and target.withholding_expected > 0:
        withheld = min(target.withholding_expected, state["open"])
    with transaction.atomic():
        doc = Document.objects.create(
            doc_type=doc_type, created_by=request.user,
            customer=target.customer if is_customer else None,
            supplier=None if is_customer else target.supplier,
            withheld_amount=withheld,
        )
        PaymentAllocation.objects.create(payment=doc, target=target,
                                         amount=state["open"])
    messages.success(request, _(
        "Payment draft for %(no)s — the open balance is allocated; pick the "
        "account and post.") % {"no": target.doc_no})
    return redirect("document_edit", pk=doc.pk)


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
        # R61: posted documents are edited field by field, on the detail
        # page — there is no longer a form that opens all of them at once.
        return redirect("document_detail", pk=doc.pk)
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
    quick_add_item = config.get("quick_add_item", False)
    return render(request, "docs/form.html", {
        "doc": doc,
        "title": config["title"],
        "form": form,
        "formsets": formsets,
        "totals_preview": _totals_preview_context(config, doc),
        "common_units": COMMON_UNITS,
        "quick_add_item": quick_add_item,
        # R49: the dialog renders the full ItemForm — D33 still hides the
        # margin fields from employees.
        "item_form": (ItemForm(is_owner=request.user.is_owner)
                      if quick_add_item else None),
    })


def editable_post_fields(user) -> set[str]:
    """R61: which ledger-free fields this user may still change on a posted
    document. Settings hide boxes here exactly as on entry forms (D106)."""
    fields = POST_EDITABLE_FIELDS - fields_hidden_by_settings()
    if not user.is_owner:
        fields -= OWNER_ONLY_POST_EDITS
    return fields


def _field_context(doc: Document, field: str) -> dict:
    return {
        "doc": doc,
        "field": field,
        "label": Document._meta.get_field(field).verbose_name,
        "value": getattr(doc, field),
    }


@login_required
def document_field_edit(request, pk, field):
    """R61: change one ledger-free field on a posted document, in place.

    The whitelist here is the same set `Document.save()` enforces (I1), so
    a field outside it cannot be written even if this view were tricked
    into naming one — the model refuses underneath.
    """
    doc = get_object_or_404(
        Document.objects.filter(status=Document.Status.POSTED), pk=pk)
    if field not in POST_EDITABLE_FIELDS - fields_hidden_by_settings():
        raise Http404
    if field in OWNER_ONLY_POST_EDITS and not request.user.is_owner:
        raise PermissionDenied
    widget = DocumentForm.Meta.widgets.get(field)
    form_class = modelform_factory(Document, fields=[field],
                                   widgets={field: widget} if widget else None)
    context = _field_context(doc, field)
    if request.method == "POST":
        before = snapshot(doc, [field])
        form = form_class(request.POST, instance=doc)
        if form.is_valid():
            saved = form.save()
            after = snapshot(saved, [field])
            if before != after:
                log_change(actor=request.user, action="DOCUMENT_FIELD_UPDATE",
                           entity="Document", entity_id=saved.pk,
                           before=before, after=after)
            return render(request, "docs/_field_value.html",
                          _field_context(saved, field))
        return render(request, "docs/_field_edit.html",
                      context | {"form": form}, status=400)
    if request.GET.get("display"):          # Cancel: put the value back
        return render(request, "docs/_field_value.html", context)
    return render(request, "docs/_field_edit.html",
                  context | {"form": form_class(instance=doc)})


@login_required
def document_detail(request, pk):
    doc = get_object_or_404(
        Document.objects.select_related(
            "customer", "supplier", "created_by", "posted_by", "voided_by",
        ),
        pk=pk,
    )
    attachments = list(doc.attachments.select_related("uploaded_by", "voided_by"))
    # D95: voiding this document takes its settling payment with it — the
    # warning has to say so by name before the owner commits.
    settled_by = list(
        Document.objects.filter(allocations_made__target=doc,
                                status=Document.Status.POSTED)
        .distinct().order_by("pk")
    ) if doc.status == Document.Status.POSTED else []
    # D98: the warning itemises every document the void will drag with it,
    # by number, so nobody discovers the blast radius afterwards.
    also_reversed = list(Document.objects.filter(
        related_document=doc,
        status=Document.Status.POSTED,
        doc_type__in=[DocType.CUSTOMER_PAYMENT, DocType.SUPPLIER_PAYMENT,
                      DocType.ADJUSTMENT, DocType.CUSTOMER_RETURN],
    ).order_by("pk")) if doc.status == Document.Status.POSTED else []
    editable = editable_post_fields(request.user) if doc.status == Document.Status.POSTED else set()
    return render(request, "docs/detail.html", {
        "doc": doc,
        # R61: one pencil per field the document still allows to change.
        "editable_fields": [_field_context(doc, name)
                            for name in POST_EDITABLE_ORDER if name in editable],
        "settled_by_numbers": ", ".join(p.doc_no or "" for p in settled_by),
        "void_also_reverses": ", ".join(
            f"{d.doc_no} — {d.get_doc_type_display()}"
            for d in settled_by + also_reversed
        ),
        "config": DOC_CONFIG.get(doc.doc_type),
        "expected": draft_expected_totals(doc),
        "settlement": settlement_context(doc),
        "attachments": [a for a in attachments if not a.is_voided],
        "voided_attachments": [a for a in attachments if a.is_voided],
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
    if layout == CompanySettings.PrintLayout.SALES_ATTACHMENT:
        lines = list(doc.lines.select_related("item", "batch"))
        return render(request, "docs/print_sales_attachment.html", {
            "company": settings,
            "doc": doc,
            "lines": lines,
            # The paper form is a fixed 20-row table; keep the shape so the
            # printout matches what the trade expects.
            "pad_range": range(len(lines) + 1, 21),
        })
    return render(request, "docs/print.html", {
        "company": settings,
        "doc": doc,
        "layout": layout,
    })


# R53: goods-out types the storeroom picks for; receivings bring goods in.
PICKING_LIST_TYPES = (DocType.SALE, DocType.PROFORMA, DocType.CONSIGNMENT_ISSUE)


@login_required
def document_picking_list(request, pk):
    """R53: a draft is printable for the storeroom long before posting gives
    it a number — as a picking list, never a watermarked invoice. No prices,
    no totals: it is not a record of a transaction (D8/D18 stay intact)."""
    doc = get_object_or_404(
        Document.objects.filter(doc_type__in=PICKING_LIST_TYPES)
        .exclude(status=Document.Status.VOIDED)
        .select_related("customer")
        .prefetch_related("lines__item", "lines__batch"),
        pk=pk,
    )
    return render(request, "docs/print_picking_list.html", {
        "company": CompanySettings.load(),
        "doc": doc,
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


def _duplicate_as_draft(source: Document, actor, reason: str) -> Document:
    """An editable copy of `source`, built from the same field lists the
    entry forms use — so whatever a doc type asks staff to type is exactly
    what gets carried over, and nothing computed at posting is.

    DOC_CONFIG is read unfiltered on purpose: a discount or pack factor
    captured before those boxes were switched off (D89) still belongs to
    the document being corrected.
    """
    config = DOC_CONFIG[source.doc_type]
    fields = {name: getattr(source, name) for name in config["fields"]}
    fields["notes"] = _("Corrects %(no)s. %(notes)s") % {
        "no": source.doc_no, "notes": fields.get("notes") or ""
    }
    draft = Document.objects.create(
        doc_type=source.doc_type, created_by=actor, corrects=source,
        correction_reason=reason, **fields,
    )
    for line in source.lines.all():
        DocumentLine.objects.create(
            document=draft,
            **{name: getattr(line, name) for name in config["lines"]},
        )
    if config.get("charges"):
        for charge in source.charges.all():
            DocumentCharge.objects.create(
                document=draft, label=charge.label, amount=charge.amount,
                is_taxable=charge.is_taxable,
            )
    if config.get("payments"):
        for payment in source.payment_lines.all():
            PaymentLine.objects.create(
                document=draft, account=payment.account,
                method=payment.method, amount=payment.amount,
            )
    if config.get("allocations"):
        for allocation in source.allocations_made.all():
            PaymentAllocation.objects.create(
                payment=draft, target=allocation.target,
                amount=allocation.amount,
            )
    return draft


@login_required
@require_POST
def document_correct(request, pk):
    """D90/D92: reopen a posted document as an editable draft.

    Nothing is reversed here. The original stays live and the copy carries a
    link back to it; posting the copy is what voids the original (D92), in
    one transaction. Walk away from the draft and nothing ever happened.
    """
    if not request.user.is_owner:
        raise PermissionDenied
    source = get_object_or_404(
        Document.objects.filter(status=Document.Status.POSTED), pk=pk,
    )
    reason = request.POST.get("reason", "").strip()
    if not reason:
        messages.error(request, _("A reason is required."))
        return redirect("document_detail", pk=source.pk)
    if source.corrections.filter(status=Document.Status.DRAFT).exists():
        messages.error(request, _(
            "A correction of %(no)s is already open. Finish or delete that "
            "draft first."
        ) % {"no": source.doc_no})
        return redirect("document_detail", pk=source.pk)
    try:
        # Advisory only — the binding check runs again when the draft is
        # posted, because the goods can move in between. Refusing here just
        # saves retyping a correction that could never land.
        get_handler(source.doc_type).check_voidable(source)
    except PostingError as exc:
        messages.error(request, str(exc))
        return redirect("document_detail", pk=source.pk)
    draft = _duplicate_as_draft(source, request.user, reason)
    messages.success(request, _(
        "Fix this copy and post it — that is when %(no)s is voided."
    ) % {"no": source.doc_no})
    return redirect("document_edit", pk=draft.pk)


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
