"""Stock models — spec §3.3: batches, cost lots, ledger (truth), balances (cache)."""

from django.db import models
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _


class Zone(models.TextChoices):
    """Where stock physically is (§2)."""

    WAREHOUSE = "WAREHOUSE", _("Warehouse")
    CONSIGNED = "CONSIGNED", _("On consignment")
    EXPIRED = "EXPIRED", _("Expired")
    UNFIT = "UNFIT", _("Unfit")
    DISPOSED = "DISPOSED", _("Disposed")


class Batch(models.Model):
    """D40: manufacturer batch — recall + expiry identity, never cost."""

    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT, related_name="batches")
    batch_no = models.CharField(_("Batch no"), max_length=60)
    expiry_date = models.DateField(_("Expiry"), null=True, blank=True)  # required iff item.has_expiry

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["item", "batch_no"], name="uniq_item_batch_no"),
        ]
        verbose_name_plural = "batches"

    def __str__(self) -> str:
        return f"{self.item.code}/{self.batch_no}"


class CostLot(models.Model):
    """D1/D40: one receipt's quantity at one frozen cost. Never overwritten."""

    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT, related_name="lots")
    batch = models.ForeignKey(Batch, null=True, blank=True, on_delete=models.PROTECT,
                              related_name="lots")
    source_line = models.ForeignKey("docs.DocumentLine", null=True, blank=True,
                                    on_delete=models.PROTECT, related_name="created_lots")
    received_at = models.DateTimeField()
    qty_received = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2)  # ※ frozen forever

    class Meta:
        ordering = ["received_at", "pk"]  # FIFO order (D40)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise NotImplementedError("Cost lots are frozen at receipt (D1); never edited.")
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"lot#{self.pk} {self.item.code} @{self.unit_cost}"


class StockLedger(models.Model):
    """Append-only movement rows (§3.3). The source of truth for stock."""

    document_line = models.ForeignKey("docs.DocumentLine", null=True, blank=True,
                                      on_delete=models.PROTECT, related_name="stock_moves")
    document = models.ForeignKey("docs.Document", on_delete=models.PROTECT,
                                 related_name="stock_moves")
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT)
    batch = models.ForeignKey(Batch, null=True, blank=True, on_delete=models.PROTECT)
    lot = models.ForeignKey(CostLot, on_delete=models.PROTECT)
    zone = models.CharField(max_length=10, choices=Zone.choices)
    consignment_customer = models.ForeignKey("catalog.Customer", null=True, blank=True,
                                             on_delete=models.PROTECT)
    qty_delta = models.IntegerField()  # + in, − out
    at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["at", "pk"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise NotImplementedError("Stock ledger is append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise NotImplementedError("Stock ledger rows are never deleted.")


class StockBalance(models.Model):
    """Derived cache (§3.3), maintained in the posting transaction. The DB CHECK
    enforces no-negative-stock (D4) even if application code is wrong."""

    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT)
    batch = models.ForeignKey(Batch, null=True, blank=True, on_delete=models.PROTECT)
    lot = models.ForeignKey(CostLot, on_delete=models.PROTECT)
    zone = models.CharField(max_length=10, choices=Zone.choices)
    consignment_customer = models.ForeignKey("catalog.Customer", null=True, blank=True,
                                             on_delete=models.PROTECT)
    qty = models.IntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(qty__gte=0), name="stock_never_negative"),
            models.UniqueConstraint(
                Coalesce("batch", 0), "lot", "zone", Coalesce("consignment_customer", 0),
                "item", name="uniq_balance_key",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.item.code} lot#{self.lot_id} {self.zone}: {self.qty}"
