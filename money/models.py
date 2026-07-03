"""Money models — spec §3.5: money/party/withholding ledgers, payment lines.
All ledgers are append-only; balances are sums, never stored columns (D11)."""

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _


class AppendOnlyModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise NotImplementedError("Ledger rows are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise NotImplementedError("Ledger rows are never deleted.")


class MoneyLedger(AppendOnlyModel):
    """D10/D11: the single source for cash/bank balances."""

    account = models.ForeignKey("catalog.Account", on_delete=models.PROTECT,
                                related_name="money_rows")
    amount_delta = models.DecimalField(max_digits=14, decimal_places=2)
    document = models.ForeignKey("docs.Document", on_delete=models.PROTECT,
                                 related_name="money_rows")
    is_reversal = models.BooleanField(default=False)  # written by void()
    at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["at", "pk"]


def account_balance(account) -> Decimal:
    """Reconciliation-grade balance: Python Decimal sum (D65 rule, kept under D66)."""
    total = Decimal("0.00")
    for amount in account.money_rows.values_list("amount_delta", flat=True):
        total += amount
    return total


class PartyLedger(AppendOnlyModel):
    """AR/AP (§3.5). AR: + is owed to us. AP: + is what we owe."""

    class PartyType(models.TextChoices):
        CUSTOMER = "CUSTOMER", _("Customer")
        SUPPLIER = "SUPPLIER", _("Supplier")

    # party_id is a polymorphic reference (Customer or Supplier pk). No DB-level
    # FK; deletion safety comes from Document.customer/.supplier PROTECT.
    party_type = models.CharField(max_length=8, choices=PartyType.choices)
    party_id = models.PositiveBigIntegerField()
    amount_delta = models.DecimalField(max_digits=14, decimal_places=2)
    document = models.ForeignKey("docs.Document", on_delete=models.PROTECT,
                                 related_name="party_rows")
    is_reversal = models.BooleanField(default=False)
    at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["at", "pk"]
        indexes = [models.Index(fields=["party_type", "party_id"])]


class WithholdingLedger(AppendOnlyModel):
    """D51/D52: withholding buckets. Never touches revenue (D53)."""

    class Direction(models.TextChoices):
        RECEIVABLE = "RECEIVABLE", _("Tax office owes us")
        PAYABLE = "PAYABLE", _("We owe the tax office")

    direction = models.CharField(max_length=10, choices=Direction.choices)
    amount_delta = models.DecimalField(max_digits=14, decimal_places=2)
    document = models.ForeignKey("docs.Document", on_delete=models.PROTECT,
                                 related_name="withholding_rows")
    certificate_no = models.CharField(max_length=60, blank=True)
    is_reversal = models.BooleanField(default=False)
    at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["at", "pk"]


class PaymentLine(models.Model):
    """D10: per-payment money splits — the source of truth for money moves."""

    class Method(models.TextChoices):
        CASH = "CASH", _("Cash")
        BANK_TRANSFER = "BANK_TRANSFER", _("Bank transfer")
        CHEQUE = "CHEQUE", _("Cheque")

    document = models.ForeignKey("docs.Document", on_delete=models.CASCADE,
                                 related_name="payment_lines")
    account = models.ForeignKey("catalog.Account", on_delete=models.PROTECT)
    method = models.CharField(max_length=13, choices=Method.choices, default=Method.CASH)
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    def save(self, *args, **kwargs):
        # Guards inserts AND updates (I1) — a locked doc accepts no new lines
        if self.document.status != "DRAFT":
            raise ValueError("Payment lines of a posted document are immutable (I1).")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.document.status != "DRAFT":
            raise ValueError("Payment lines of a posted document are immutable (I1).")
        super().delete(*args, **kwargs)


class PaymentAllocation(models.Model):
    """D3/D44: which invoice(s) a payment settles. Partial allowed."""

    payment = models.ForeignKey("docs.Document", on_delete=models.CASCADE,
                                related_name="allocations_made")
    target = models.ForeignKey("docs.Document", on_delete=models.PROTECT,
                               related_name="allocations_received")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
