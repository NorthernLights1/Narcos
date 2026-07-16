"""Document forms for the implemented posting handlers."""

from django import forms
from django.db.models import F, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from catalog.models import Item
from docs.handlers_sales import issue_line_value
from docs.models import DocType, Document, DocumentCharge, DocumentLine
from docs.tax import round2
from money.models import PaymentAllocation, PaymentLine
from stock.models import Batch, CostLot, Zone


def _selling_price(item: Item):
    """D23: maintained price, or latest lot cost × (1 + margin%) for AUTO
    items. On master-priced documents (D80) this IS the line price — the
    browser's value is ignored; elsewhere it is only the prefill hint."""
    if (item.pricing_mode == Item.PricingMode.AUTO
            and item.auto_margin_pct is not None):
        latest_cost = getattr(item, "latest_cost", None)
        if latest_cost:
            return round2(latest_cost * (1 + item.auto_margin_pct / 100))
    return item.maintained_price


class ItemSelect(forms.Select):
    """Item options carry price/unit/VAT data for the client-side preview
    and prefill (display only — posting snapshots everything server-side)."""

    def create_option(self, name, value, label, selected, index,
                      subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index,
                                       subindex=subindex, attrs=attrs)
        item = getattr(value, "instance", None)
        if item is not None:
            option["attrs"]["data-vat-exempt"] = "1" if item.vat_exempt else "0"
            option["attrs"]["data-base-unit"] = item.base_unit
            price = _selling_price(item)
            if price is not None:
                option["attrs"]["data-price"] = str(price)
        return option


class BatchSelect(forms.Select):
    """Batch options carry item id (for dependent filtering), expiry, and
    warehouse on-hand so the picked batch's context stays visible."""

    def create_option(self, name, value, label, selected, index,
                      subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index,
                                       subindex=subindex, attrs=attrs)
        batch = getattr(value, "instance", None)
        if batch is not None:
            option["attrs"]["data-item"] = str(batch.item_id)
            if batch.expiry_date:
                option["attrs"]["data-expiry"] = batch.expiry_date.isoformat()
            option["attrs"]["data-onhand"] = str(getattr(batch, "warehouse_qty", None) or 0)
        return option


def _batch_label(batch: Batch) -> str:
    expiry = batch.expiry_date.isoformat() if batch.expiry_date else _("no expiry")
    on_hand = batch.warehouse_qty or 0
    return f"{batch.item.code} · {batch.batch_no} · {expiry} · {on_hand}"


DOC_CONFIG = {
    DocType.RECEIVING: {
        "title": _("Receiving"),
        # due_date = supplier credit terms; feeds AP overdue on the dashboard
        "fields": ["supplier", "supplier_invoice_date", "due_date", "notes"],
        "lines": [
            "item", "batch_no_entered", "expiry_entered", "unit_label", "factor",
            "qty_entered", "unit_cost_entered", "free_qty",
        ],
        "payments": True,
    },
    DocType.SALE: {
        "title": _("Sale"),
        "fields": [
            "customer", "sale_kind", "due_date", "doc_discount",
            "customer_will_withhold", "fiscal_receipt_no", "machine_total", "notes",
        ],
        "lines": ["item", "batch", "unit_label", "factor", "qty_entered",
                  "unit_price", "line_discount"],
        "charges": True,
        "payments": True,
        "master_priced": True,  # D80: price comes from the item, not the keyboard
    },
    DocType.PROFORMA: {
        "title": _("Proforma"),
        "fields": ["customer", "doc_discount", "notes"],
        "lines": ["item", "batch", "unit_label", "factor", "qty_entered",
                  "unit_price", "line_discount"],
        "charges": True,
        "master_priced": True,  # D80
    },
    DocType.CONSIGNMENT_ISSUE: {
        "title": _("Consignment issue"),
        # D70: the withholding decision is made here, not at settlement —
        # it depends on who the buyer is (PLC), known when goods go out.
        "fields": ["customer", "due_date", "doc_discount",
                   "customer_will_withhold", "notes"],
        "lines": ["item", "batch", "unit_label", "factor", "qty_entered",
                  "unit_price", "line_discount"],
        "master_priced": True,  # D80 — the CN-000002 lesson
    },
    DocType.CONSIGNMENT_SETTLEMENT: {
        "title": _("Consignment settlement"),
        # No withholding checkbox: inherited from the issue at posting (D70)
        "fields": [
            "customer", "related_document", "sale_kind", "due_date", "doc_discount",
            "fiscal_receipt_no", "machine_total", "notes",
        ],
        # No unit/factor/price: settlement quantities are base units and the
        # money comes from the issue's own prices (§7.5).
        "lines": [
            "item", "batch", "qty_entered",
            "qty_sold", "qty_returned", "qty_expired_unfit", "target_zone",
        ],
        "payments": True,
    },
    DocType.CUSTOMER_RETURN: {
        "title": _("Customer return"),
        "fields": [
            "customer", "related_document", "doc_discount",
            "fiscal_receipt_no", "machine_total", "notes",
        ],
        "lines": [
            "item", "batch", "unit_label", "factor", "qty_entered", "unit_price",
            "unit_cost_entered", "line_discount", "target_zone",
        ],
        "payments": True,
    },
    DocType.SUPPLIER_RETURN: {
        "title": _("Supplier return"),
        "fields": ["supplier", "notes"],
        "lines": ["item", "lot", "unit_label", "factor", "qty_entered"],
        "payments": True,
    },
    DocType.CUSTOMER_PAYMENT: {
        "title": _("Customer payment"),
        "fields": ["customer", "withheld_amount", "withholding_certificate_no", "notes"],
        "payments": True,
        "allocations": True,
    },
    DocType.SUPPLIER_PAYMENT: {
        "title": _("Supplier payment"),
        "fields": ["supplier", "withheld_amount", "withholding_certificate_no", "notes"],
        "payments": True,
        "allocations": True,
    },
    DocType.WHT_REMITTANCE: {
        "title": _("Withholding remittance"),
        "fields": ["withholding_certificate_no", "notes"],
        "payments": True,
    },
    DocType.EXPENSE: {
        "title": _("Expense"),
        "fields": ["expense_category", "payee", "grand_total", "notes"],
        "payments": True,
    },
    DocType.TRANSFER: {
        "title": _("Transfer"),
        "fields": ["from_account", "to_account", "grand_total", "notes"],
    },
    DocType.ZONE_MOVE: {
        "title": _("Zone move"),
        "fields": ["notes"],
        "lines": ["item", "lot", "source_zone", "target_zone",
                  "unit_label", "factor", "qty_entered"],
    },
    DocType.ADJUSTMENT: {
        "title": _("Adjustment"),
        "fields": ["notes"],
        "lines": ["item", "batch", "source_zone", "qty_delta", "unit_cost_entered"],
    },
    DocType.STOCK_COUNT: {
        "title": _("Stock count"),
        "fields": ["notes"],
        "lines": ["item", "batch", "lot", "qty_base", "qty_entered"],
    },
    DocType.OPENING_STOCK: {
        "title": _("Opening stock"),
        "fields": ["document_date", "notes"],
        "lines": [
            "item", "batch_no_entered", "expiry_entered", "unit_label", "factor",
            "qty_entered", "unit_cost_entered",
        ],
    },
    DocType.OPENING_EXPIRED: {
        "title": _("Opening expired/unfit"),
        "fields": ["document_date", "notes"],
        "lines": [
            "item", "batch_no_entered", "expiry_entered", "unit_label", "factor",
            "qty_entered", "unit_cost_entered", "target_zone",
        ],
    },
    DocType.OPENING_CONSIGNMENT: {
        "title": _("Opening consignment"),
        "fields": ["customer", "document_date", "due_date", "notes"],
        "lines": [
            "item", "batch_no_entered", "expiry_entered", "unit_label", "factor",
            "qty_entered", "unit_cost_entered", "unit_price",
        ],
    },
    DocType.OPENING_AR: {
        "title": _("Opening receivable"),
        "fields": ["customer", "document_date", "due_date", "grand_total", "notes"],
    },
    DocType.OPENING_AP: {
        "title": _("Opening payable"),
        "fields": ["supplier", "document_date", "due_date", "grand_total", "notes"],
    },
    DocType.OPENING_CASH: {
        "title": _("Opening cash"),
        "fields": ["document_date", "notes"],
        "payments": True,
    },
}

IMPLEMENTED_DOC_TYPES = tuple(DOC_CONFIG)


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = [
            "customer", "supplier", "sale_kind", "due_date", "supplier_invoice_date",
            "document_date", "doc_discount", "customer_will_withhold", "withheld_amount",
            "withholding_certificate_no", "fiscal_receipt_no", "machine_total",
            "expense_category", "payee", "from_account", "to_account",
            "related_document", "grand_total", "notes",
        ]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "document_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "supplier_invoice_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={
                "rows": 3, "placeholder": _("Optional notes for this transaction…"),
            }),
            "payee": forms.TextInput(attrs={
                "placeholder": _("Who received the money, e.g. Ethio Telecom"),
            }),
            "fiscal_receipt_no": forms.TextInput(attrs={
                "placeholder": _("Number printed on the fiscal receipt"),
            }),
            "machine_total": forms.NumberInput(attrs={
                "placeholder": _("Total shown by the fiscal machine"),
            }),
            "withholding_certificate_no": forms.TextInput(attrs={
                "placeholder": _("Serial no. on the withholding certificate"),
            }),
        }
        help_texts = {
            "withheld_amount": _(
                "Only when the payer kept back withholding tax: copy the "
                "amount printed on the certificate they hand you. Leave 0 "
                "otherwise."
            ),
            "withholding_certificate_no": _(
                "The serial number printed on that certificate."
            ),
        }

    SEARCHABLE = ("customer", "supplier", "expense_category", "from_account",
                  "to_account", "related_document")

    def __init__(self, *args, doc_type: str, **kwargs):
        super().__init__(*args, **kwargs)
        keep = set(DOC_CONFIG[doc_type]["fields"])
        for name in list(self.fields):
            if name not in keep:
                del self.fields[name]
        if "related_document" in self.fields:
            source_types = ([DocType.CONSIGNMENT_ISSUE, DocType.OPENING_CONSIGNMENT]
                            if doc_type == DocType.CONSIGNMENT_SETTLEMENT
                            else [DocType.SALE])
            self.fields["related_document"].queryset = Document.objects.filter(
                doc_type__in=source_types, status=Document.Status.POSTED,
            ).order_by("-posted_at")
        for name in self.SEARCHABLE:
            if name in self.fields:
                self.fields[name].widget.attrs["data-search"] = "1"


class DocumentReferenceForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["fiscal_receipt_no", "machine_total", "withholding_certificate_no"]


class DocumentLineForm(forms.ModelForm):
    source_zone = forms.ChoiceField(
        choices=[
            (Zone.WAREHOUSE, _("Warehouse")),
            (Zone.EXPIRED, _("Expired")),
            (Zone.UNFIT, _("Unfit")),
        ],
        required=False,
    )
    target_zone = forms.ChoiceField(
        choices=[
            (Zone.WAREHOUSE, _("Warehouse")),
            (Zone.EXPIRED, _("Expired")),
            (Zone.UNFIT, _("Unfit")),
            (Zone.DISPOSED, _("Disposed")),
        ],
        required=False,
    )

    class Meta:
        model = DocumentLine
        fields = [
            "item", "batch", "batch_no_entered", "expiry_entered", "lot",
            "unit_label", "factor", "qty_entered", "qty_base", "unit_price",
            "unit_cost_entered", "free_qty", "line_discount", "qty_sold",
            "qty_returned", "qty_expired_unfit", "qty_delta", "source_zone",
            "target_zone",
        ]
        widgets = {
            "expiry_entered": forms.DateInput(attrs={"type": "date"}),
            "item": ItemSelect,
            "batch": BatchSelect,
            "batch_no_entered": forms.TextInput(attrs={
                "placeholder": _("batch no, e.g. B0425"),
            }),
            "unit_label": forms.TextInput(attrs={
                "placeholder": _("e.g. box"), "list": "unit-options",
            }),
            "qty_entered": forms.NumberInput(attrs={"placeholder": _("qty")}),
            "unit_cost_entered": forms.NumberInput(attrs={
                "placeholder": _("what you paid per unit"),
            }),
        }
        labels = {
            "unit_cost_entered": _("Cost paid / unit"),
            "unit_price": _("Selling price / unit"),
        }

    def __init__(self, *args, line_fields: list[str], issue=None,
                 master_priced: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._master_priced = master_priced
        keep = set(line_fields)
        for name in list(self.fields):
            if name not in keep:
                del self.fields[name]
        if "qty_base" in self.fields:
            self.fields["qty_base"].disabled = True
        if master_priced and "unit_price" in self.fields:
            # D80: the price is the item's price — shown, never typed. The
            # server recomputes it in clean(); discounts are how you charge less.
            self.fields["unit_price"].required = False
            self.fields["unit_price"].widget.attrs.update({
                "readonly": True, "tabindex": "-1",
                "title": _("Comes from the item — use a discount to charge less."),
            })
        if "qty_sold" in self.fields:
            # Settlement split (D6): "still out" is informational; the three
            # split quantities are what staff enter, in base units.
            self.fields["qty_entered"].label = _("Still out")
            self.fields["qty_entered"].widget.attrs["readonly"] = True
            self.fields["qty_sold"].label = _("Sold")
            if issue is not None and self.instance.pk:
                # The issue's frozen price feeds the live money preview (§7.5)
                value = issue_line_value(issue, self.instance.item_id,
                                         self.instance.batch_id)
                if value is not None:
                    per_base, is_taxable = value
                    attrs = self.fields["qty_sold"].widget.attrs
                    attrs["data-value-per-base"] = str(per_base)
                    attrs["data-taxable"] = "1" if is_taxable else "0"
            self.fields["qty_returned"].label = _("Returned")
            self.fields["qty_expired_unfit"].label = _("Expired/damaged")
            self.fields["target_zone"].label = _("Damaged goes to")
            self.fields["target_zone"].choices = [
                ("", "---------"),
                (Zone.EXPIRED, _("Expired")),
                (Zone.UNFIT, _("Unfit")),
            ]
        if "item" in self.fields:
            # Latest lot cost feeds the AUTO price prefill (D23)
            latest = (CostLot.objects.filter(item=OuterRef("pk"))
                      .order_by("-received_at", "-pk").values("unit_cost")[:1])
            self.fields["item"].queryset = Item.objects.annotate(
                latest_cost=Subquery(latest)
            )
        if "batch" in self.fields:
            # Label shows item · batch no · expiry · warehouse on-hand, so the
            # picker carries the shelf context (display only; D4 still guards).
            self.fields["batch"].queryset = (
                Batch.objects.select_related("item")
                .annotate(warehouse_qty=Sum(
                    "stockbalance__qty",
                    filter=Q(stockbalance__zone=Zone.WAREHOUSE),
                ))
                .order_by("item__code", "expiry_date", "batch_no")
            )
            self.fields["batch"].label_from_instance = _batch_label
        for name in ("item", "batch", "lot"):
            if name in self.fields:
                self.fields[name].widget.attrs["data-search"] = "1"

    def clean(self):
        data = super().clean()
        item = data.get("item")
        if self._master_priced and item is not None:
            # D80: whatever the browser sent, the line sells at the item's
            # price. An item without a usable price cannot be sold at all.
            price = _selling_price(item)
            if not price or price <= 0:
                self.add_error("item", _(
                    "%(name)s has no selling price yet — set a maintained "
                    "price on the item, or receive stock first for "
                    "auto-margin items.") % {"name": item.name})
            else:
                data["unit_price"] = price
        return data


def _allocation_label(target: Document) -> str:
    """`GRN-000001 · Care · open 2,900.00 of 4,900.00` — the open balance is
    annotated onto the queryset; display only, the handler re-checks under
    lock at posting (I13)."""
    party = target.customer or target.supplier
    open_amount = target.grand_total - (target.settled or 0)
    label = f"{target.doc_no} · {party.name if party else '—'} · "
    if open_amount == target.grand_total:
        label += _("open %(o)s") % {"o": f"{open_amount:,.2f}"}
    else:
        label += _("open %(o)s of %(t)s") % {
            "o": f"{open_amount:,.2f}", "t": f"{target.grand_total:,.2f}"}
    if target.withholding_expected > 0:
        # Cross-check hint: the customer's certificate should match this
        label += " · " + _("WHT expected %(w)s") % {
            "w": f"{target.withholding_expected:,.2f}"}
    return label


class AllocationTargetSelect(forms.Select):
    """Target options carry the open balance, expected withholding, and party
    so the client can prefill the allocation amount, the withheld field, and
    an empty customer/supplier box (D72/D74)."""

    def create_option(self, name, value, label, selected, index,
                      subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index,
                                       subindex=subindex, attrs=attrs)
        target = getattr(value, "instance", None)
        if target is not None:
            option["attrs"]["data-open"] = str(
                target.grand_total - (target.settled or 0))
            if target.withholding_expected > 0:
                option["attrs"]["data-wht"] = str(target.withholding_expected)
            if target.customer_id:
                option["attrs"]["data-customer"] = str(target.customer_id)
            elif target.supplier_id:
                option["attrs"]["data-supplier"] = str(target.supplier_id)
        return option


class PaymentAllocationForm(forms.ModelForm):
    class Meta:
        model = PaymentAllocation
        fields = ["target", "amount"]
        widgets = {
            "target": AllocationTargetSelect,
            "amount": forms.NumberInput(attrs={"placeholder": _("0.00")}),
        }

    def __init__(self, *args, doc_type: str, customer_id=None, supplier_id=None,
                 **kwargs):
        super().__init__(*args, **kwargs)
        target_types = {
            DocType.CUSTOMER_PAYMENT: [
                DocType.SALE, DocType.CONSIGNMENT_SETTLEMENT, DocType.OPENING_AR,
            ],
            DocType.SUPPLIER_PAYMENT: [DocType.RECEIVING, DocType.OPENING_AP],
        }.get(doc_type)
        qs = Document.objects.filter(status=Document.Status.POSTED)
        if target_types:
            qs = qs.filter(doc_type__in=target_types)
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        if supplier_id:
            qs = qs.filter(supplier_id=supplier_id)
        # Only invoices that still have an open balance are offered
        qs = qs.select_related("customer", "supplier").annotate(
            settled=Sum("allocations_received__amount",
                        filter=Q(allocations_received__payment__status=Document.Status.POSTED)),
        ).exclude(grand_total__lte=Coalesce(F("settled"), 0))
        self.fields["target"].queryset = qs.order_by("-posted_at", "-pk")
        self.fields["target"].label_from_instance = _allocation_label
        self.fields["target"].widget.attrs["data-search"] = "1"


LineFormSet = inlineformset_factory(
    Document, DocumentLine, form=DocumentLineForm, extra=5, can_delete=True
)
ChargeFormSet = inlineformset_factory(
    Document, DocumentCharge, fields=["label", "amount", "is_taxable"],
    extra=2, can_delete=True,
    widgets={
        "label": forms.TextInput(attrs={"placeholder": _("e.g. Delivery fee")}),
        "amount": forms.NumberInput(attrs={"placeholder": _("0.00")}),
    },
)
PaymentLineFormSet = inlineformset_factory(
    Document, PaymentLine, fields=["account", "method", "amount"],
    extra=3, can_delete=True,
    widgets={"amount": forms.NumberInput(attrs={"placeholder": _("0.00")})},
)
PaymentAllocationFormSet = inlineformset_factory(
    Document, PaymentAllocation, form=PaymentAllocationForm, fk_name="payment",
    extra=3, can_delete=True,
)


def formsets_for(doc: Document, data=None):
    config = DOC_CONFIG[doc.doc_type]
    formsets = []
    if config.get("lines"):
        line_kwargs = {"line_fields": config["lines"],
                       "master_priced": config.get("master_priced", False)}
        if doc.doc_type == DocType.CONSIGNMENT_SETTLEMENT and doc.related_document_id:
            line_kwargs["issue"] = doc.related_document
        formsets.append((
            "lines", _("Lines"),
            LineFormSet(
                data, instance=doc, prefix="lines", form_kwargs=line_kwargs,
            ),
        ))
    if config.get("charges"):
        formsets.append((
            "charges", _("Charges"),
            ChargeFormSet(data, instance=doc, prefix="charges"),
        ))
    if config.get("payments"):
        formsets.append((
            "payments", _("Payment lines"),
            PaymentLineFormSet(data, instance=doc, prefix="payments"),
        ))
    if config.get("allocations"):
        formsets.append((
            "allocations", _("Allocations"),
            PaymentAllocationFormSet(
                data, instance=doc, prefix="allocations",
                form_kwargs={
                    "doc_type": doc.doc_type,
                    # Once the draft has a party, offer only their invoices
                    "customer_id": doc.customer_id,
                    "supplier_id": doc.supplier_id,
                },
            ),
        ))
    return formsets
