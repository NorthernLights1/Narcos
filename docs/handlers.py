"""Stock-document handlers: Receiving (§7.1) and Supplier return (§7.7).
Registered via DocsConfig.ready()."""

from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone
from django.utils.translation import gettext as _

from docs.models import DocType, Document, LotConsumption
from docs.posting import Effects, Handler, PostingError, StockDelta, register
from stock.models import Batch, CostLot, StockBalance, Zone

TWO_DP = Decimal("0.01")


def round2(value: Decimal) -> Decimal:
    return value.quantize(TWO_DP, rounding=ROUND_HALF_UP)


class ReceivingHandler(Handler):
    """GRN: stock + WAREHOUSE (new lots, D1/D40), bonus goods lower unit cost
    (D21), AP + (credit; cash-now auto-payment arrives with P5). Void per D5."""

    def validate(self, doc: Document) -> None:
        if doc.supplier_id is None:
            raise PostingError(_("Receiving needs a supplier."))
        lines = list(doc.lines.select_related("item"))
        if not lines:
            raise PostingError(_("Receiving needs at least one line."))
        for line in lines:
            item = line.item
            if line.qty_entered + line.free_qty <= 0:
                raise PostingError(_("Line %(item)s: quantity must be positive.")
                                   % {"item": item.code})
            if line.factor < 1:
                raise PostingError(_("Line %(item)s: bad unit factor.") % {"item": item.code})
            if line.unit_cost_entered is None or line.unit_cost_entered < 0:
                raise PostingError(_("Line %(item)s: unit cost is required (D42).")
                                   % {"item": item.code})
            if item.is_batch_tracked:
                if not line.batch_no_entered.strip():
                    raise PostingError(_("Line %(item)s: batch number required (D29).")
                                       % {"item": item.code})
                if item.has_expiry and line.expiry_entered is None:
                    raise PostingError(_("Line %(item)s: expiry date required (D22).")
                                       % {"item": item.code})
                if not item.has_expiry and line.expiry_entered is not None:
                    raise PostingError(_("Line %(item)s: item has no expiry (D22).")
                                       % {"item": item.code})
            else:
                if line.batch_no_entered or line.expiry_entered:
                    raise PostingError(_("Line %(item)s: item is not batch tracked (D29).")
                                       % {"item": item.code})

    def build_effects(self, doc: Document) -> Effects:
        effects = Effects()
        now = timezone.now()
        total_paid = Decimal("0.00")
        for line in doc.lines.select_related("item"):
            item = line.item
            batch = None
            if item.is_batch_tracked:
                batch, created = Batch.objects.get_or_create(
                    item=item, batch_no=line.batch_no_entered.strip(),
                    defaults={"expiry_date": line.expiry_entered},
                )
                if not created and batch.expiry_date != line.expiry_entered:
                    # §7.1: same batch_no with a different expiry is an entry error
                    raise PostingError(
                        _("Batch %(no)s of %(item)s already exists with expiry "
                          "%(old)s — you entered %(new)s. Check the entry.")
                        % {"no": batch.batch_no, "item": item.code,
                           "old": batch.expiry_date, "new": line.expiry_entered}
                    )
            paid_base = line.qty_entered * line.factor
            free_base = line.free_qty * line.factor
            total_base = paid_base + free_base
            amount_paid = round2(Decimal(line.qty_entered) * line.unit_cost_entered)
            # D21: actual unit cost = amount paid ÷ ALL units received (paid + free)
            lot_cost = round2(amount_paid / total_base) if total_base else Decimal("0.00")
            lot = CostLot.objects.create(
                item=item, batch=batch, source_line=line, received_at=now,
                qty_received=total_base, unit_cost=lot_cost,
            )
            line.batch = batch
            line.qty_base = total_base
            line.line_net = amount_paid
            line.save()
            effects.stock.append(StockDelta(
                item_id=item.pk, lot_id=lot.pk, zone=Zone.WAREHOUSE,
                qty_delta=total_base, batch_id=batch.pk if batch else None,
                line_id=line.pk,
            ))
            total_paid += amount_paid
        doc.subtotal = total_paid
        doc.grand_total = total_paid  # no tax on receivings (D63)
        if total_paid > 0:
            effects.party.append(("SUPPLIER", doc.supplier_id, total_paid))  # AP +
        return effects

    def check_voidable(self, doc: Document) -> None:
        """D5: once any part of a receiving was sold or moved, void is blocked
        outright — every created lot must still sit whole in WAREHOUSE."""
        for lot in CostLot.objects.filter(source_line__document=doc):
            in_warehouse = (
                StockBalance.objects.filter(lot=lot, zone=Zone.WAREHOUSE)
                .values_list("qty", flat=True).first() or 0
            )
            if in_warehouse != lot.qty_received:
                raise PostingError(
                    _("Cannot void: goods from this receiving were already "
                      "sold or moved (D5). Use a supplier return or owner "
                      "adjustment instead.")
                )


class SupplierReturnHandler(Handler):
    """SR (§7.7/D41): stock − WAREHOUSE from picked lots at frozen lot cost;
    AP − by default, or money + when refund payment lines are present."""

    def validate(self, doc: Document) -> None:
        if doc.supplier_id is None:
            raise PostingError(_("Supplier return needs a supplier."))
        lines = list(doc.lines.select_related("item", "lot"))
        if not lines:
            raise PostingError(_("Supplier return needs at least one line."))
        for line in lines:
            if line.lot_id is None:
                raise PostingError(_("Line %(item)s: pick the lot being returned.")
                                   % {"item": line.item.code})
            if line.lot.item_id != line.item_id:
                raise PostingError(_("Line %(item)s: lot belongs to a different item.")
                                   % {"item": line.item.code})
            if line.qty_entered <= 0:
                raise PostingError(_("Line %(item)s: quantity must be positive.")
                                   % {"item": line.item.code})

    def build_effects(self, doc: Document) -> Effects:
        effects = Effects()
        total = Decimal("0.00")
        for line in doc.lines.select_related("item", "lot"):
            lot = line.lot
            qty_base = line.qty_entered * line.factor
            value = round2(Decimal(qty_base) * lot.unit_cost)
            line.qty_base = qty_base
            line.line_net = value
            line.batch = lot.batch
            line.save()
            LotConsumption.objects.create(line=line, lot=lot, qty=qty_base,
                                          unit_cost=lot.unit_cost)
            effects.stock.append(StockDelta(
                item_id=line.item_id, lot_id=lot.pk, zone=Zone.WAREHOUSE,
                qty_delta=-qty_base, batch_id=lot.batch_id, line_id=line.pk,
            ))
            total += value
        doc.subtotal = total
        doc.grand_total = total
        refund_lines = list(doc.payment_lines.all())
        if refund_lines:
            refunded = sum((p.amount for p in refund_lines), Decimal("0.00"))
            if refunded != total:
                raise PostingError(
                    _("Refund lines (%(r)s) must equal the return value (%(t)s).")
                    % {"r": refunded, "t": total}
                )
            for p in refund_lines:
                effects.money.append((p.account_id, p.amount))  # refund received
        else:
            effects.party.append(("SUPPLIER", doc.supplier_id, -total))  # AP −
        return effects


register(DocType.RECEIVING, ReceivingHandler())
register(DocType.SUPPLIER_RETURN, SupplierReturnHandler())
