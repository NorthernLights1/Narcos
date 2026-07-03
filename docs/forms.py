"""Document forms for the implemented posting handlers."""

from django import forms
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from docs.models import DocType, Document, DocumentCharge, DocumentLine
from money.models import PaymentAllocation, PaymentLine
from stock.models import Zone


DOC_CONFIG = {
    DocType.RECEIVING: {
        "title": _("Receiving"),
        "fields": ["supplier", "supplier_invoice_date", "notes"],
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
    },
    DocType.PROFORMA: {
        "title": _("Proforma"),
        "fields": ["customer", "doc_discount", "notes"],
        "lines": ["item", "batch", "unit_label", "factor", "qty_entered",
                  "unit_price", "line_discount"],
        "charges": True,
    },
    DocType.CONSIGNMENT_ISSUE: {
        "title": _("Consignment issue"),
        "fields": ["customer", "due_date", "doc_discount", "notes"],
        "lines": ["item", "batch", "unit_label", "factor", "qty_entered",
                  "unit_price", "line_discount"],
    },
    DocType.CONSIGNMENT_SETTLEMENT: {
        "title": _("Consignment settlement"),
        "fields": [
            "customer", "related_document", "sale_kind", "due_date", "doc_discount",
            "customer_will_withhold", "fiscal_receipt_no", "machine_total", "notes",
        ],
        "lines": [
            "item", "batch", "unit_label", "factor", "qty_entered",
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
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

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
        }

    def __init__(self, *args, line_fields: list[str], **kwargs):
        super().__init__(*args, **kwargs)
        keep = set(line_fields)
        for name in list(self.fields):
            if name not in keep:
                del self.fields[name]
        if "qty_base" in self.fields:
            self.fields["qty_base"].disabled = True


class PaymentAllocationForm(forms.ModelForm):
    class Meta:
        model = PaymentAllocation
        fields = ["target", "amount"]

    def __init__(self, *args, doc_type: str, **kwargs):
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
        self.fields["target"].queryset = qs.order_by("-posted_at", "-pk")


LineFormSet = inlineformset_factory(
    Document, DocumentLine, form=DocumentLineForm, extra=5, can_delete=True
)
ChargeFormSet = inlineformset_factory(
    Document, DocumentCharge, fields=["label", "amount", "is_taxable"],
    extra=2, can_delete=True,
)
PaymentLineFormSet = inlineformset_factory(
    Document, PaymentLine, fields=["account", "method", "amount"],
    extra=3, can_delete=True,
)
PaymentAllocationFormSet = inlineformset_factory(
    Document, PaymentAllocation, form=PaymentAllocationForm, fk_name="payment",
    extra=3, can_delete=True
)


def formsets_for(doc: Document, data=None):
    config = DOC_CONFIG[doc.doc_type]
    formsets = []
    if config.get("lines"):
        formsets.append((
            "lines", _("Lines"),
            LineFormSet(
                data, instance=doc, prefix="lines",
                form_kwargs={"line_fields": config["lines"]},
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
                form_kwargs={"doc_type": doc.doc_type},
            ),
        ))
    return formsets
