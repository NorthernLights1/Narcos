"""Document models — spec §3.4. Documents are the only thing that changes
ledgers. Posted documents are immutable (D28/I1) except §7.12 reference fields."""

from pathlib import Path
from uuid import uuid4

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ImmutableDocumentError(Exception):
    """Raised on any attempt to change a posted document's frozen fields (I1)."""


class DocType(models.TextChoices):
    RECEIVING = "RECEIVING", _("Receiving")
    SALE = "SALE", _("Sale")
    PROFORMA = "PROFORMA", _("Proforma")
    CONSIGNMENT_ISSUE = "CONSIGNMENT_ISSUE", _("Consignment issue")
    CONSIGNMENT_SETTLEMENT = "CONSIGNMENT_SETTLEMENT", _("Consignment settlement")
    CUSTOMER_RETURN = "CUSTOMER_RETURN", _("Customer return")
    SUPPLIER_RETURN = "SUPPLIER_RETURN", _("Supplier return")
    CUSTOMER_PAYMENT = "CUSTOMER_PAYMENT", _("Customer payment")
    SUPPLIER_PAYMENT = "SUPPLIER_PAYMENT", _("Supplier payment")
    WHT_REMITTANCE = "WHT_REMITTANCE", _("Withholding remittance")
    TRANSFER = "TRANSFER", _("Transfer")
    EXPENSE = "EXPENSE", _("Expense")
    ZONE_MOVE = "ZONE_MOVE", _("Zone move")
    ADJUSTMENT = "ADJUSTMENT", _("Adjustment")
    STOCK_COUNT = "STOCK_COUNT", _("Stock count")
    OPENING_STOCK = "OPENING_STOCK", _("Opening stock")
    OPENING_AR = "OPENING_AR", _("Opening receivable")
    OPENING_AP = "OPENING_AP", _("Opening payable")
    OPENING_CASH = "OPENING_CASH", _("Opening cash")
    OPENING_CONSIGNMENT = "OPENING_CONSIGNMENT", _("Opening consignment")
    OPENING_EXPIRED = "OPENING_EXPIRED", _("Opening expired/unfit")


# §7 table + §3.1: doc numbers are per type, format PREFIX-000123
PREFIXES = {
    DocType.RECEIVING: "GRN", DocType.SALE: "SI", DocType.PROFORMA: "PF",
    DocType.CONSIGNMENT_ISSUE: "CN", DocType.CONSIGNMENT_SETTLEMENT: "CS",
    DocType.CUSTOMER_RETURN: "CR", DocType.SUPPLIER_RETURN: "SR",
    DocType.CUSTOMER_PAYMENT: "RC", DocType.SUPPLIER_PAYMENT: "PV",
    DocType.WHT_REMITTANCE: "WR", DocType.TRANSFER: "TR", DocType.EXPENSE: "EX",
    DocType.ZONE_MOVE: "ZM", DocType.ADJUSTMENT: "ADJ", DocType.STOCK_COUNT: "SC",
    DocType.OPENING_STOCK: "OP", DocType.OPENING_AR: "OP", DocType.OPENING_AP: "OP",
    DocType.OPENING_CASH: "OP", DocType.OPENING_CONSIGNMENT: "OP",
    DocType.OPENING_EXPIRED: "OP",
}

# §7.12: the only fields editable after posting (reference-only, audited)
POST_EDITABLE_FIELDS = {"fiscal_receipt_no", "machine_total", "withholding_certificate_no"}
# Fields the void path itself must write (attnames — the diff compares attnames,
# so the FK must appear here as voided_by_id, not voided_by)
VOID_FIELDS = {"status", "voided_by_id", "voided_at", "void_reason"}


class Document(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", _("Draft")
        POSTED = "POSTED", _("Posted")
        VOIDED = "VOIDED", _("Voided")

    class SaleKind(models.TextChoices):
        CASH = "CASH", _("Cash")
        CREDIT = "CREDIT", _("Credit")

    doc_type = models.CharField(max_length=25, choices=DocType.choices)
    doc_no = models.CharField(max_length=15, null=True, blank=True)  # D8: only at posting
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.DRAFT)
    document_date = models.DateTimeField(null=True, blank=True)  # D38: system time at posting

    customer = models.ForeignKey("catalog.Customer", null=True, blank=True,
                                 on_delete=models.PROTECT, related_name="documents")
    supplier = models.ForeignKey("catalog.Supplier", null=True, blank=True,
                                 on_delete=models.PROTECT, related_name="documents")

    sale_kind = models.CharField(max_length=6, choices=SaleKind.choices, blank=True)
    due_date = models.DateField(null=True, blank=True)  # D38 exc. 3
    supplier_invoice_date = models.DateField(null=True, blank=True)  # D38 exc. 2

    # Totals ※ (D32) — tax_total is authoritative, never recomputed elsewhere
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    doc_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    taxable_base = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    exempt_base = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_rate_snapshot = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # §5 ※

    customer_will_withhold = models.BooleanField(default=False)  # D51 checkbox
    withholding_expected = models.DecimalField(  # D51, display only
        max_digits=14, decimal_places=2, default=0
    )
    withheld_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)  # §3.5
    withholding_certificate_no = models.CharField(max_length=60, blank=True)  # §7.12

    fiscal_receipt_no = models.CharField(max_length=60, blank=True)  # D18/D43, §7.12
    machine_total = models.DecimalField(max_digits=14, decimal_places=2,
                                        null=True, blank=True)

    # EXPENSE (§7.9)
    expense_category = models.ForeignKey("catalog.ExpenseCategory", null=True, blank=True,
                                         on_delete=models.PROTECT)
    payee = models.CharField(max_length=200, blank=True)
    # TRANSFER (D9)
    from_account = models.ForeignKey("catalog.Account", null=True, blank=True,
                                     on_delete=models.PROTECT, related_name="transfers_out")
    to_account = models.ForeignKey("catalog.Account", null=True, blank=True,
                                   on_delete=models.PROTECT, related_name="transfers_in")

    # CR → original SALE, CS → CONSIGNMENT_ISSUE, proforma → converted SALE
    related_document = models.ForeignKey("self", null=True, blank=True,
                                         on_delete=models.PROTECT,
                                         related_name="related_documents")

    created_by = models.ForeignKey("core.User", on_delete=models.PROTECT,
                                   related_name="documents_created")
    created_at = models.DateTimeField(auto_now_add=True)
    posted_by = models.ForeignKey("core.User", null=True, blank=True,
                                  on_delete=models.PROTECT, related_name="documents_posted")
    posted_at = models.DateTimeField(null=True, blank=True, db_index=True)  # clock-anomaly hot path
    voided_by = models.ForeignKey("core.User", null=True, blank=True,
                                  on_delete=models.PROTECT, related_name="documents_voided")
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=300, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["doc_type", "doc_no"], name="uniq_doc_no_per_type",
                                    condition=models.Q(doc_no__isnull=False)),
        ]
        indexes = [models.Index(fields=["doc_type", "status"])]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            old = type(self).objects.get(pk=self.pk)
            if old.status == self.Status.POSTED:
                changed = {
                    f.attname for f in self._meta.concrete_fields
                    if getattr(old, f.attname) != getattr(self, f.attname)
                }
                allowed = POST_EDITABLE_FIELDS | VOID_FIELDS
                if changed - allowed:
                    raise ImmutableDocumentError(
                        f"Posted document {old.doc_no} is immutable; "
                        f"attempted to change: {sorted(changed - allowed)} (I1)"
                    )
                # Write only the changed fields so two staff editing different
                # §7.12 reference fields never clobber each other.
                kwargs.setdefault("update_fields", sorted(changed))
            elif old.status == self.Status.VOIDED:
                raise ImmutableDocumentError("Voided documents are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status != self.Status.DRAFT:
            raise ImmutableDocumentError("Only drafts can be deleted (D28).")
        super().delete(*args, **kwargs)

    def __str__(self) -> str:
        return self.doc_no or f"{self.doc_type} draft #{self.pk}"


class DocumentLine(models.Model):
    """§3.4. ※ fields freeze at posting; lines never change afterwards."""

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT)
    batch = models.ForeignKey("stock.Batch", null=True, blank=True, on_delete=models.PROTECT)
    # Receiving drafts carry the raw batch entry; the Batch row is get-or-created
    # at posting (§7.1). Returns/moves pick a specific source lot (§7.7).
    batch_no_entered = models.CharField(max_length=60, blank=True)
    expiry_entered = models.DateField(null=True, blank=True)
    lot = models.ForeignKey("stock.CostLot", null=True, blank=True,
                            on_delete=models.PROTECT, related_name="+")
    unit_label = models.CharField(max_length=50)  # ※
    factor = models.PositiveIntegerField(default=1)  # ※ D62
    qty_entered = models.PositiveIntegerField()
    qty_base = models.PositiveIntegerField(default=0)  # ※ = qty_entered × factor
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)  # ※
    unit_cost_entered = models.DecimalField(  # receivings (D42); paid amount basis for D21
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    free_qty = models.PositiveIntegerField(default=0)  # D21 bonus units (entered unit)
    line_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)  # ※
    line_net = models.DecimalField(max_digits=14, decimal_places=2, default=0)  # ※
    is_taxable = models.BooleanField(default=True)  # ※ snapshot (D30/D50)
    cogs_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)  # ※ D33
    # Settlement split (D6)
    qty_sold = models.PositiveIntegerField(default=0)
    qty_returned = models.PositiveIntegerField(default=0)
    qty_expired_unfit = models.PositiveIntegerField(default=0)
    # Stock ops: signed adjustment qty and source/target zones
    qty_delta = models.IntegerField(default=0)
    source_zone = models.CharField(max_length=10, blank=True)
    target_zone = models.CharField(max_length=10, blank=True)

    def _document_is_locked(self) -> bool:
        return self.document.status != Document.Status.DRAFT

    def save(self, *args, **kwargs):
        # Guards inserts AND updates: nothing may be attached to a locked doc (I1)
        if self._document_is_locked():
            raise ImmutableDocumentError("Lines of a posted document are immutable (I1).")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self._document_is_locked():
            raise ImmutableDocumentError("Lines of a posted document are immutable (I1).")
        super().delete(*args, **kwargs)


class DocumentCharge(models.Model):
    """D37: non-item charges billed to the customer (sales/proforma only)."""

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="charges")
    label = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    is_taxable = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if self.document.status != Document.Status.DRAFT:
            raise ImmutableDocumentError("Charges of a posted document are immutable (I1).")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.document.status != Document.Status.DRAFT:
            raise ImmutableDocumentError("Charges of a posted document are immutable (I1).")
        super().delete(*args, **kwargs)


class LotConsumption(models.Model):
    """§3.4: which cost lots a line consumed — drives COGS, void, returns."""

    line = models.ForeignKey(DocumentLine, on_delete=models.PROTECT,
                             related_name="lot_consumptions")
    lot = models.ForeignKey("stock.CostLot", on_delete=models.PROTECT,
                            related_name="consumptions")
    qty = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2)  # ※

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise NotImplementedError("Lot consumptions are frozen at posting.")
        if self.line.document.status != Document.Status.DRAFT:
            # Consumptions are written during posting, while the doc is still
            # DRAFT in the DB; anything later is tampering (I1).
            raise ImmutableDocumentError("Cannot attach consumptions to a locked document.")
        super().save(*args, **kwargs)


# Attachments: which files we accept and how much. Magic-byte prefixes are
# checked on upload so a renamed .exe can't sneak in as a "pdf".
ATTACHMENT_TYPES = {
    ".pdf": ("application/pdf", (b"%PDF",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".webp": ("image/webp", (b"RIFF",)),
}
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS_PER_DOC = 10


def attachment_path(_instance, filename: str) -> str:
    """Server-generated storage name — the user's filename is metadata only
    and never touches the filesystem (path traversal)."""
    ext = Path(filename).suffix.lower()
    return f"attachments/{timezone.now():%Y/%m}/{uuid4().hex}{ext}"


class Attachment(models.Model):
    """Scanned evidence for a document (supplier invoice, delivery note,
    certificate). Follows the void pattern: physically deletable only while
    the parent is a DRAFT; once posted, the owner may void (hide + audit)
    but the bytes are never destroyed."""

    document = models.ForeignKey(Document, on_delete=models.CASCADE,
                                 related_name="attachments")
    file = models.FileField(upload_to=attachment_path)
    original_name = models.CharField(max_length=200)
    size = models.PositiveIntegerField()
    note = models.CharField(_("Note"), max_length=200, blank=True)
    uploaded_by = models.ForeignKey("core.User", on_delete=models.PROTECT,
                                    related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_voided = models.BooleanField(default=False)
    voided_by = models.ForeignKey("core.User", on_delete=models.PROTECT,
                                  null=True, blank=True, related_name="+")
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["uploaded_at", "pk"]

    def __str__(self) -> str:
        return self.original_name

    @property
    def content_type(self) -> str:
        ext = Path(self.file.name).suffix.lower()
        return ATTACHMENT_TYPES.get(ext, ("application/octet-stream", ()))[0]
