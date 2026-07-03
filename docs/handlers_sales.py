"""Sales-side handlers: Sale (§7.2), Proforma (§7.3), Customer return (§7.6).
Registered via DocsConfig.ready()."""

from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext as _

from core.audit import log_event
from core.models import CompanySettings
from docs.checks import ExpiryStatus, credit_check, expiry_status
from docs.models import DocType, Document, LotConsumption
from docs.posting import Effects, Handler, PostingError, StockDelta, register
from docs.tax import Part, TaxError, compute_totals, round2
from stock.models import CostLot, StockBalance, Zone


def _line_parts(doc: Document) -> tuple[list, list[Part]]:
    """Freeze per-line nets + taxable flags; returns (lines, parts) where
    parts also include charges (D37), in that order."""
    lines = list(doc.lines.select_related("item", "batch"))
    parts = []
    for line in lines:
        line.qty_base = line.qty_entered * line.factor
        gross = Decimal(line.qty_entered) * line.unit_price
        if line.line_discount > gross:
            raise PostingError(_("Line %(item)s: discount exceeds the line amount.")
                               % {"item": line.item.code})
        line.line_net = round2(gross - line.line_discount)
        line.is_taxable = not line.item.vat_exempt  # ※ snapshot (D30/D50)
        parts.append(Part(value=line.line_net, is_taxable=line.is_taxable))
    charges = list(doc.charges.all())
    for charge in charges:
        if charge.amount < 0:
            raise PostingError(_("Charges cannot be negative."))
        parts.append(Part(value=charge.amount, is_taxable=charge.is_taxable))
    return lines, parts


def _freeze_totals(doc: Document, parts: list[Part], settings) -> None:
    """§5 — the only tax computation. Freezes ※ totals onto the document."""
    try:
        totals = compute_totals(parts, doc.doc_discount,
                                settings.tax_regime,
                                settings.vat_rate if settings.tax_regime == "VAT"
                                else settings.tot_rate)
    except TaxError as exc:
        raise PostingError(str(exc))
    doc.subtotal = totals.subtotal
    doc.taxable_base = totals.taxable_base
    doc.exempt_base = totals.exempt_base
    doc.tax_total = totals.tax_total
    doc.grand_total = totals.grand_total
    doc.tax_rate_snapshot = (settings.vat_rate if settings.tax_regime == "VAT"
                             else settings.tot_rate if settings.tax_regime == "TOT"
                             else Decimal("0.00"))


def _consume_fifo(line, qty_base: int) -> list[StockDelta]:
    """D40: within the line's batch (or batchless for untracked items),
    consume WAREHOUSE lots oldest-first. Writes LotConsumption ※ and the
    line's cogs_total. Raises when stock is insufficient."""
    lots = CostLot.objects.filter(item_id=line.item_id, batch_id=line.batch_id
                                  ).order_by("received_at", "pk")
    deltas = []
    remaining = qty_base
    cogs = Decimal("0.00")
    for lot in lots:
        if remaining == 0:
            break
        available = (
            StockBalance.objects.filter(lot=lot, zone=Zone.WAREHOUSE)
            .values_list("qty", flat=True).first() or 0
        )
        if available <= 0:
            continue
        take = min(available, remaining)
        LotConsumption.objects.create(line=line, lot=lot, qty=take,
                                      unit_cost=lot.unit_cost)
        cogs += Decimal(take) * lot.unit_cost
        deltas.append(StockDelta(
            item_id=line.item_id, lot_id=lot.pk, zone=Zone.WAREHOUSE,
            qty_delta=-take, batch_id=line.batch_id, line_id=line.pk,
        ))
        remaining -= take
    if remaining > 0:
        raise PostingError(
            _("Not enough stock for %(item)s: short by %(n)d base units.")
            % {"item": line.item.code, "n": remaining}
        )
    line.cogs_total = round2(cogs)
    return deltas


class SaleHandler(Handler):
    """SI (§7.2): stock − via FIFO lots, §5 tax, cash → money +, credit → AR +."""

    def validate(self, doc: Document) -> None:
        if doc.customer_id is None:
            raise PostingError(_("Sale needs a customer."))
        if doc.sale_kind not in (Document.SaleKind.CASH, Document.SaleKind.CREDIT):
            raise PostingError(_("Sale must be cash or credit."))
        if doc.sale_kind == Document.SaleKind.CREDIT and doc.due_date is None:
            raise PostingError(_("Credit sale needs a due date (D38 exc. 3)."))
        lines = list(doc.lines.select_related("item", "batch"))
        if not lines:
            raise PostingError(_("Sale needs at least one line."))
        today = timezone.localdate()
        settings = CompanySettings.load()
        for line in lines:
            if line.qty_entered <= 0:
                raise PostingError(_("Line %(item)s: quantity must be positive.")
                                   % {"item": line.item.code})
            if line.unit_price < 0 or line.line_discount < 0:
                raise PostingError(_("Line %(item)s: negative amounts not allowed.")
                                   % {"item": line.item.code})
            if line.item.is_batch_tracked and line.batch_id is None:
                raise PostingError(_("Line %(item)s: pick a batch (D29).")
                                   % {"item": line.item.code})
            if line.batch_id is not None:
                status = expiry_status(line.batch.expiry_date, today,
                                       settings.near_expiry_months)
                if status == ExpiryStatus.EXPIRED:
                    raise PostingError(  # D46: block, no override
                        _("Batch %(no)s of %(item)s is expired — sale blocked (D46).")
                        % {"no": line.batch.batch_no, "item": line.item.code}
                    )

    def build_effects(self, doc: Document) -> Effects:
        settings = CompanySettings.load()
        lines, parts = _line_parts(doc)
        _freeze_totals(doc, parts, settings)

        # D51: expected withholding, display only — never touches the ledgers here
        if settings.withholding_on_sales and doc.customer_will_withhold:
            doc.withholding_expected = round2(
                settings.withholding_rate / 100 * (doc.grand_total - doc.tax_total)
            )

        # D25/§8: credit exposure check (cash sales never count). Lock the
        # customer row first so two concurrent credit sales for the same
        # customer serialize and can't both slip under the limit.
        if doc.sale_kind == Document.SaleKind.CREDIT:
            from catalog.models import Customer

            customer = Customer.objects.select_for_update().get(pk=doc.customer_id)
            action, message = credit_check(customer, settings, doc.grand_total)
            if action == "BLOCK" and not getattr(doc, "_override_reason", ""):
                raise PostingError(message + " " + _("Owner override required (D25)."))
            if action in ("WARN", "BLOCK"):
                log_event(doc.created_by, f"CREDIT_{action}", "Document", doc.pk,
                          {"message": message})

        effects = Effects()
        for line in lines:
            effects.stock.extend(_consume_fifo(line, line.qty_base))
            line.save()

        if doc.sale_kind == Document.SaleKind.CASH:
            payments = list(doc.payment_lines.all())
            paid = sum((p.amount for p in payments), Decimal("0.00"))
            if paid != doc.grand_total:
                raise PostingError(
                    _("Cash sale: payment lines (%(p)s) must equal the total (%(t)s).")
                    % {"p": paid, "t": doc.grand_total}
                )
            for p in payments:
                effects.money.append((p.account_id, p.amount))
        else:
            effects.party.append(("CUSTOMER", doc.customer_id, doc.grand_total))  # AR +
        return effects


class ProformaHandler(Handler):
    """PF (§7.3): §5 totals frozen for print, zero ledger effect."""

    def validate(self, doc: Document) -> None:
        if doc.customer_id is None:
            raise PostingError(_("Proforma needs a customer."))
        lines = list(doc.lines.select_related("item"))
        if not lines:
            raise PostingError(_("Proforma needs at least one line."))
        for line in lines:
            if line.qty_entered <= 0:
                raise PostingError(_("Line %(item)s: quantity must be positive.")
                                   % {"item": line.item.code})
            if line.unit_price < 0 or line.line_discount < 0:
                raise PostingError(_("Line %(item)s: negative amounts not allowed.")
                                   % {"item": line.item.code})

    def build_effects(self, doc: Document) -> Effects:
        settings = CompanySettings.load()
        lines, parts = _line_parts(doc)
        _freeze_totals(doc, parts, settings)
        for line in lines:
            line.save()
        return Effects()  # no stock, no money, no AR


class CustomerReturnHandler(Handler):
    """CR (§7.6/D41): stock back as a NEW lot at original COGS cost, refund
    (money −) or AR credit (party −). Totals stored positive; reports treat
    the CR doc type as negative (I11)."""

    RETURN_ZONES = (Zone.WAREHOUSE, Zone.EXPIRED, Zone.UNFIT)

    def validate(self, doc: Document) -> None:
        if doc.customer_id is None:
            raise PostingError(_("Customer return needs a customer."))
        lines = list(doc.lines.select_related("item"))
        if not lines:
            raise PostingError(_("Customer return needs at least one line."))
        if doc.related_document is not None:
            if doc.related_document.doc_type != DocType.SALE \
                    or doc.related_document.status != Document.Status.POSTED:
                raise PostingError(_("Return must reference a posted sale."))
            if doc.related_document.customer_id != doc.customer_id:
                raise PostingError(_("Return customer differs from the sale's."))
        elif not doc.created_by.is_owner:
            # §7.6: without a sale reference the owner enters the cost
            raise PostingError(_("Returns without a sale reference are owner-only."))
        for line in lines:
            if line.qty_entered <= 0:
                raise PostingError(_("Line %(item)s: quantity must be positive.")
                                   % {"item": line.item.code})
            if line.target_zone not in self.RETURN_ZONES:
                raise PostingError(
                    _("Line %(item)s: destination must be warehouse, expired or unfit.")
                    % {"item": line.item.code})
            if line.item.is_batch_tracked and line.batch_id is None:
                raise PostingError(_("Line %(item)s: pick the batch returned (D29).")
                                   % {"item": line.item.code})

    @staticmethod
    def _sale_totals(sale: Document, item_id, batch_id) -> tuple[int, Decimal, object]:
        """Aggregate the sale's matching lines (a sale may legally carry the
        same item+batch on several lines): (qty sold, total cogs, first line)."""
        matching = list(sale.lines.filter(item_id=item_id, batch_id=batch_id)
                        .order_by("pk"))
        qty_sold = sum(line.qty_base for line in matching)
        cogs = sum((line.cogs_total for line in matching), Decimal("0.00"))
        return qty_sold, cogs, matching[0] if matching else None

    @staticmethod
    def _already_returned(sale: Document, item_id, batch_id) -> int:
        """Base units already returned against this sale by POSTED returns."""
        from django.db.models import Sum

        from docs.models import DocumentLine

        return (
            DocumentLine.objects.filter(
                document__related_document=sale,
                document__doc_type=DocType.CUSTOMER_RETURN,
                document__status=Document.Status.POSTED,
                item_id=item_id, batch_id=batch_id,
            ).aggregate(total=Sum("qty_base"))["total"] or 0
        )

    def build_effects(self, doc: Document) -> Effects:
        settings = CompanySettings.load()
        now = timezone.now()
        sale = None
        if doc.related_document_id is not None:
            # Serialize returns against the same sale: two concurrent CRs must
            # not both pass the cumulative-quantity cap (review-gate CRITICAL).
            sale = Document.objects.select_for_update().get(pk=doc.related_document_id)
        lines = list(doc.lines.select_related("item", "batch"))
        parts = []
        effects = Effects()
        requested: dict[tuple, int] = {}  # cumulative within THIS document too
        for line in lines:
            line.qty_base = line.qty_entered * line.factor
            original = None
            if sale is not None:
                key = (line.item_id, line.batch_id)
                qty_sold, sale_cogs, original = self._sale_totals(
                    sale, line.item_id, line.batch_id)
                if original is None:
                    raise PostingError(
                        _("Line %(item)s: the referenced sale has no such "
                          "item/batch.") % {"item": line.item.code})
                requested[key] = requested.get(key, 0) + line.qty_base
                already = self._already_returned(sale, line.item_id, line.batch_id)
                if requested[key] + already > qty_sold:
                    raise PostingError(
                        _("Line %(item)s: returning more than remains returnable "
                          "on the sale (%(left)d of %(sold)d base units left).")
                        % {"item": line.item.code,
                           "left": max(qty_sold - already, 0), "sold": qty_sold})
                if not line.unit_price:
                    line.unit_price = original.unit_price
                line.is_taxable = original.is_taxable  # snapshot from the sale
            else:
                line.is_taxable = not line.item.vat_exempt
            gross = Decimal(line.qty_entered) * line.unit_price
            line.line_net = round2(gross - line.line_discount)
            parts.append(Part(value=line.line_net, is_taxable=line.is_taxable))

            # §7.6: original COGS unit cost — weighted over the sale's matching
            # lines when referenced; owner-entered cost otherwise
            if sale is not None and qty_sold:
                cost = round2(sale_cogs / qty_sold)
            elif line.unit_cost_entered is not None:
                cost = line.unit_cost_entered
            else:
                raise PostingError(
                    _("Line %(item)s: enter the unit cost (no sale reference).")
                    % {"item": line.item.code})
            lot = CostLot.objects.create(
                item=line.item, batch=line.batch, source_line=line,
                received_at=now, qty_received=line.qty_base, unit_cost=cost,
            )
            line.cogs_total = round2(Decimal(line.qty_base) * cost)
            line.save()
            effects.stock.append(StockDelta(
                item_id=line.item_id, lot_id=lot.pk, zone=line.target_zone,
                qty_delta=line.qty_base, batch_id=line.batch_id, line_id=line.pk,
            ))

        _freeze_totals(doc, parts, settings)

        refunds = list(doc.payment_lines.all())
        if refunds:
            refunded = sum((p.amount for p in refunds), Decimal("0.00"))
            if refunded != doc.grand_total:
                raise PostingError(
                    _("Refund lines (%(r)s) must equal the return total (%(t)s).")
                    % {"r": refunded, "t": doc.grand_total})
            for p in refunds:
                effects.money.append((p.account_id, -p.amount))  # cash out
        else:
            effects.party.append(("CUSTOMER", doc.customer_id, -doc.grand_total))  # AR −
        return effects


register(DocType.SALE, SaleHandler())
register(DocType.PROFORMA, ProformaHandler())
register(DocType.CUSTOMER_RETURN, CustomerReturnHandler())
