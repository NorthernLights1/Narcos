"""Payment handlers: RC (customer payment), PV (supplier payment), WR
(withholding remittance). §7.8/§7.9, D3/D10/D44, withholding per §6.
Registered via DocsConfig.ready()."""

from decimal import Decimal

from django.db.models import Sum
from django.utils.translation import gettext as _

from core.models import CompanySettings
from docs.models import DocType, Document
from docs.posting import Effects, Handler, PostingError, register
from docs.tax import round2
from money.models import PaymentAllocation, WithholdingLedger

# Which posted document types carry an open AR/AP balance a payment can settle
AR_TARGET_TYPES = {DocType.SALE, DocType.CONSIGNMENT_SETTLEMENT, DocType.OPENING_AR}
AP_TARGET_TYPES = {DocType.RECEIVING, DocType.OPENING_AP}


def open_balance(target: Document) -> Decimal:
    """Invoice's unsettled remainder: grand_total − allocations from POSTED
    payments (voided payments drop out via the status filter)."""
    allocated = (
        PaymentAllocation.objects.filter(
            target=target, payment__status=Document.Status.POSTED
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    )
    return target.grand_total - allocated


def withholding_balance(direction: str) -> Decimal:
    total = Decimal("0.00")
    rows = WithholdingLedger.objects.filter(direction=direction) \
        .values_list("amount_delta", flat=True)
    for amount in rows:
        total += amount
    return total


class _PaymentBase(Handler):
    """Shared RC/PV logic. Subclasses set the party side + ledger directions."""

    party_type: str  # CUSTOMER | SUPPLIER
    target_types: set
    withholding_setting: str  # settings flag name
    withholding_direction: str  # RECEIVABLE | PAYABLE
    money_sign: int  # +1 money in (RC), −1 money out (PV)

    def _party_id(self, doc: Document) -> int:
        raise NotImplementedError

    def validate(self, doc: Document) -> None:
        if self._party_id(doc) is None:
            raise PostingError(_("Payment needs a party."))
        settings = CompanySettings.load()
        if doc.withheld_amount < 0:
            raise PostingError(_("Withheld amount cannot be negative."))
        if doc.withheld_amount > 0 and not getattr(settings, self.withholding_setting):
            raise PostingError(_("Withholding is disabled in settings (D51/D52)."))
        lines = list(doc.payment_lines.all())
        if any(line.amount <= 0 for line in lines):
            raise PostingError(_("Every payment line must be positive."))
        total = sum((line.amount for line in lines), Decimal("0.00")) + doc.withheld_amount
        if total <= 0:
            raise PostingError(_("Payment needs money lines or a withheld amount."))
        allocations = list(doc.allocations_made.all())
        if not allocations:
            raise PostingError(_("Payment must be allocated to invoices (D3)."))
        if any(a.amount <= 0 for a in allocations):
            raise PostingError(_("Every allocation must be positive."))
        allocated = sum((a.amount for a in allocations), Decimal("0.00"))
        if allocated != total:
            # D44: no advances/overpayments — allocations equal the payment exactly
            raise PostingError(
                _("Allocations (%(a)s) must equal the payment total (%(t)s) — "
                  "advances and overpayments are not supported (D44).")
                % {"a": allocated, "t": total})

    def build_effects(self, doc: Document) -> Effects:
        allocations = list(doc.allocations_made.select_related("target").order_by("target_id"))
        # Lock targets in stable pk order, then re-check open balances under lock
        # so two concurrent payments can't both settle the same invoice (I13).
        targets = {
            t.pk: t for t in Document.objects.select_for_update()
            .filter(pk__in=[a.target_id for a in allocations])
        }
        per_target: dict[int, Decimal] = {}
        for allocation in allocations:
            per_target[allocation.target_id] = (
                per_target.get(allocation.target_id, Decimal("0.00")) + allocation.amount
            )
        party_id = self._party_id(doc)
        for target_id, amount in per_target.items():
            target = targets[target_id]
            if target.status != Document.Status.POSTED:
                raise PostingError(_("Allocation target %(no)s is not posted.")
                                   % {"no": target.doc_no or target.pk})
            if target.doc_type not in self.target_types:
                raise PostingError(_("Documents of type %(t)s cannot be settled here.")
                                   % {"t": target.doc_type})
            if target.doc_type in (DocType.SALE, DocType.CONSIGNMENT_SETTLEMENT) \
                    and target.sale_kind != Document.SaleKind.CREDIT \
                    and doc.related_document_id != target.pk:
                raise PostingError(_("Cash documents can only be settled by their auto payment."))
            if self._target_party_id(target) != party_id:
                raise PostingError(_("Allocation target %(no)s belongs to another party.")
                                   % {"no": target.doc_no})
            remaining = open_balance(target)
            if amount > remaining:
                raise PostingError(
                    _("Allocation to %(no)s (%(a)s) exceeds its open balance (%(r)s).")
                    % {"no": target.doc_no, "a": amount, "r": remaining})

        lines = list(doc.payment_lines.all())
        cash_total = sum((line.amount for line in lines), Decimal("0.00"))
        total = cash_total + doc.withheld_amount
        doc.grand_total = total

        effects = Effects()
        for line in lines:
            effects.money.append((line.account_id, self.money_sign * line.amount))
        # The invoice settles for cash + withheld together (D51/D52); linked
        # cash-now documents have no AR/AP row to reverse.
        party_delta = Decimal("0.00")
        for allocation in allocations:
            if self._target_has_party_balance(doc, targets[allocation.target_id]):
                party_delta -= allocation.amount
        if party_delta:
            effects.party.append((self.party_type, party_id, party_delta))
        if doc.withheld_amount > 0:
            effects.withholding.append((
                self.withholding_direction, doc.withheld_amount,
                doc.withholding_certificate_no,
            ))
        return effects

    def _target_party_id(self, target: Document) -> int:
        raise NotImplementedError

    def _target_has_party_balance(self, doc: Document, target: Document) -> bool:
        if target.doc_type in (DocType.SALE, DocType.CONSIGNMENT_SETTLEMENT):
            return target.sale_kind == Document.SaleKind.CREDIT
        if target.doc_type == DocType.RECEIVING and doc.related_document_id == target.pk:
            return False
        return True

    def check_voidable(self, doc: Document) -> None:
        if doc.related_document_id and doc.related_document.status == Document.Status.POSTED:
            raise PostingError(_("Void the source document; its auto payment will void with it."))


class CustomerPaymentHandler(_PaymentBase):
    """RC (§6 sales side, D51): customer pays; they may keep back the
    withholding % and hand us a certificate instead."""

    party_type = "CUSTOMER"
    target_types = AR_TARGET_TYPES
    withholding_setting = "withholding_on_sales"
    withholding_direction = "RECEIVABLE"
    money_sign = +1

    def _party_id(self, doc):
        return doc.customer_id

    def _target_party_id(self, target):
        return target.customer_id


class SupplierPaymentHandler(_PaymentBase):
    """PV (§6 purchase side, D52): we pay the supplier; when we are a
    withholding agent we keep back the % and owe it to the tax office."""

    party_type = "SUPPLIER"
    target_types = AP_TARGET_TYPES
    withholding_setting = "withholding_on_purchases"
    withholding_direction = "PAYABLE"
    money_sign = -1

    def _party_id(self, doc):
        return doc.supplier_id

    def _target_party_id(self, target):
        return target.supplier_id


class WhtRemittanceHandler(Handler):
    """WR (§7.9): pay the withholding-payable bucket to the tax office —
    money −, withholding PAYABLE −. Normally monthly (D52)."""

    def validate(self, doc: Document) -> None:
        lines = list(doc.payment_lines.all())
        if not lines:
            raise PostingError(_("Remittance needs at least one payment line."))
        if any(line.amount <= 0 for line in lines):
            raise PostingError(_("Every payment line must be positive."))
        total = sum((line.amount for line in lines), Decimal("0.00"))
        payable = withholding_balance("PAYABLE")
        if total > payable:
            raise PostingError(
                _("Remitting %(t)s but only %(p)s is owed to the tax office.")
                % {"t": total, "p": payable})

    def build_effects(self, doc: Document) -> Effects:
        effects = Effects()
        total = Decimal("0.00")
        for line in doc.payment_lines.all():
            effects.money.append((line.account_id, -line.amount))
            total += line.amount
        doc.grand_total = round2(total)
        effects.withholding.append(("PAYABLE", -total, doc.withholding_certificate_no))
        return effects


register(DocType.CUSTOMER_PAYMENT, CustomerPaymentHandler())
register(DocType.SUPPLIER_PAYMENT, SupplierPaymentHandler())
register(DocType.WHT_REMITTANCE, WhtRemittanceHandler())
