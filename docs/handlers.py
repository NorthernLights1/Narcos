"""Stock-document handlers: Receiving (§7.1) and Supplier return (§7.7).
Registered via DocsConfig.ready()."""

from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone
from django.utils.translation import gettext as _

from core.audit import log_event
from docs.models import DocType, Document, DocumentLine, LotConsumption
from docs.posting import Effects, Handler, PostingError, StockDelta, register
from stock.models import Batch, CostLot, StockBalance, StockLedger, Zone

TWO_DP = Decimal("0.01")


def round2(value: Decimal) -> Decimal:
    return value.quantize(TWO_DP, rounding=ROUND_HALF_UP)


WAREHOUSE_ZONES = (Zone.WAREHOUSE, Zone.EXPIRED, Zone.UNFIT)


def _zone_qty(lot, zone: str) -> int:
    return (
        StockBalance.objects.filter(lot=lot, zone=zone)
        .values_list("qty", flat=True).first() or 0
    )


def _latest_cost(item_id: int, batch_id=None) -> Decimal:
    lot = CostLot.objects.filter(item_id=item_id, batch_id=batch_id).order_by("-received_at", "-pk").first()
    return lot.unit_cost if lot else Decimal("0.00")


def _consume_zone_fifo(line, zone: str, qty: int) -> list[StockDelta]:
    lots = CostLot.objects.filter(item_id=line.item_id, batch_id=line.batch_id).order_by("received_at", "pk")
    remaining = qty
    deltas = []
    cogs = Decimal("0.00")
    for lot in lots:
        if remaining == 0:
            break
        available = _zone_qty(lot, zone)
        if available <= 0:
            continue
        take = min(available, remaining)
        remaining -= take
        cogs += Decimal(take) * lot.unit_cost
        LotConsumption.objects.create(line=line, lot=lot, qty=take, unit_cost=lot.unit_cost)
        deltas.append(StockDelta(
            item_id=line.item_id, lot_id=lot.pk, zone=zone, qty_delta=-take,
            batch_id=line.batch_id, line_id=line.pk,
        ))
    if remaining:
        raise PostingError(_("Not enough stock for %(item)s in %(zone)s.")
                           % {"item": line.item.code, "zone": zone})
    line.cogs_total = round2(cogs)
    return deltas


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
        for payment in doc.payment_lines.all():
            if payment.amount <= 0:
                raise PostingError(_("Every payment line must be positive."))

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
        payments = list(doc.payment_lines.all())
        if payments:
            paid = sum((payment.amount for payment in payments), Decimal("0.00"))
            if paid != total_paid:
                raise PostingError(
                    _("Receiving payment lines (%(p)s) must equal the total (%(t)s).")
                    % {"p": paid, "t": total_paid}
                )
        elif total_paid > 0:
            effects.party.append(("SUPPLIER", doc.supplier_id, total_paid))  # AP +
        return effects

    def after_post(self, doc: Document, actor) -> None:
        payments = list(doc.payment_lines.all())
        if not payments:
            return
        from docs.posting import post
        from money.models import PaymentAllocation, PaymentLine

        payment = Document.objects.create(
            doc_type=DocType.SUPPLIER_PAYMENT,
            created_by=actor,
            supplier=doc.supplier,
            related_document=doc,
            notes=_("Auto payment for %(no)s") % {"no": doc.doc_no},
        )
        for line in payments:
            PaymentLine.objects.create(
                document=payment,
                account=line.account,
                method=line.method,
                amount=line.amount,
            )
        PaymentAllocation.objects.create(payment=payment, target=doc, amount=doc.grand_total)
        post(payment, actor)

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


class ZoneMoveHandler(Handler):
    """ZM: move existing lot quantities between warehouse-side zones."""

    def validate(self, doc: Document) -> None:
        lines = list(doc.lines.select_related("item", "lot"))
        if not lines:
            raise PostingError(_("Zone move needs at least one line."))
        for line in lines:
            if line.lot_id is None:
                raise PostingError(_("Line %(item)s: pick the lot to move.")
                                   % {"item": line.item.code})
            if line.lot.item_id != line.item_id:
                raise PostingError(_("Line %(item)s: lot belongs to a different item.")
                                   % {"item": line.item.code})
            if line.source_zone not in WAREHOUSE_ZONES:
                raise PostingError(_("Line %(item)s: source must be our warehouse stock.")
                                   % {"item": line.item.code})
            if line.target_zone == Zone.DISPOSED \
                    and not getattr(doc, "_posting_actor", doc.created_by).is_owner:
                raise PostingError(_("Only the owner can dispose stock (D28)."))
            if line.target_zone not in (Zone.EXPIRED, Zone.UNFIT, Zone.DISPOSED):
                raise PostingError(_("Line %(item)s: bad destination zone.")
                                   % {"item": line.item.code})
            if line.source_zone == line.target_zone:
                raise PostingError(_("Line %(item)s: source and destination must differ.")
                                   % {"item": line.item.code})
            if line.qty_entered <= 0:
                raise PostingError(_("Line %(item)s: quantity must be positive.")
                                   % {"item": line.item.code})

    def build_effects(self, doc: Document) -> Effects:
        effects = Effects()
        total = Decimal("0.00")
        for line in doc.lines.select_related("item", "lot"):
            qty_base = line.qty_entered * line.factor
            line.batch = line.lot.batch
            line.qty_base = qty_base
            line.cogs_total = round2(Decimal(qty_base) * line.lot.unit_cost)
            line.save()
            effects.stock.append(StockDelta(
                item_id=line.item_id, lot_id=line.lot_id, zone=line.source_zone,
                qty_delta=-qty_base, batch_id=line.lot.batch_id, line_id=line.pk,
            ))
            effects.stock.append(StockDelta(
                item_id=line.item_id, lot_id=line.lot_id, zone=line.target_zone,
                qty_delta=qty_base, batch_id=line.lot.batch_id, line_id=line.pk,
            ))
            total += line.cogs_total
        doc.subtotal = total
        doc.grand_total = total
        return effects


class AdjustmentHandler(Handler):
    """ADJ: owner-only stock correction; positive creates lots, negative FIFO consumes."""

    def validate(self, doc: Document) -> None:
        if not getattr(doc, "_posting_actor", doc.created_by).is_owner:
            raise PostingError(_("Only the owner can post adjustments (D28)."))
        if not doc.notes.strip():
            raise PostingError(_("Adjustment reason is required."))
        lines = list(doc.lines.select_related("item", "batch"))
        if not lines:
            raise PostingError(_("Adjustment needs at least one line."))
        for line in lines:
            if line.qty_delta == 0:
                raise PostingError(_("Line %(item)s: adjustment quantity cannot be zero.")
                                   % {"item": line.item.code})
            if line.source_zone not in WAREHOUSE_ZONES:
                raise PostingError(_("Line %(item)s: zone must be warehouse, expired or unfit.")
                                   % {"item": line.item.code})
            if line.item.is_batch_tracked and line.batch_id is None:
                raise PostingError(_("Line %(item)s: pick a batch (D29).")
                                   % {"item": line.item.code})
            if line.qty_delta > 0 and line.unit_cost_entered is not None \
                    and line.unit_cost_entered < 0:
                raise PostingError(_("Line %(item)s: unit cost cannot be negative.")
                                   % {"item": line.item.code})

    def build_effects(self, doc: Document) -> Effects:
        effects = Effects()
        now = timezone.now()
        total = Decimal("0.00")
        for line in doc.lines.select_related("item", "batch"):
            zone = line.source_zone
            if line.qty_delta > 0:
                cost = line.unit_cost_entered
                if cost is None:
                    cost = _latest_cost(line.item_id, line.batch_id)
                lot = CostLot.objects.create(
                    item=line.item, batch=line.batch, source_line=line,
                    received_at=now, qty_received=line.qty_delta, unit_cost=cost,
                )
                line.qty_base = line.qty_delta
                line.cogs_total = round2(Decimal(line.qty_delta) * cost)
                line.save()
                effects.stock.append(StockDelta(
                    item_id=line.item_id, lot_id=lot.pk, zone=zone,
                    qty_delta=line.qty_delta, batch_id=line.batch_id, line_id=line.pk,
                ))
            else:
                qty = -line.qty_delta
                line.qty_base = qty
                if line.lot_id:
                    if _zone_qty(line.lot, zone) < qty:
                        raise PostingError(_("Not enough stock for %(item)s in %(zone)s.")
                                           % {"item": line.item.code, "zone": zone})
                    line.batch = line.lot.batch
                    line.cogs_total = round2(Decimal(qty) * line.lot.unit_cost)
                    LotConsumption.objects.create(line=line, lot=line.lot, qty=qty,
                                                  unit_cost=line.lot.unit_cost)
                    effects.stock.append(StockDelta(
                        item_id=line.item_id, lot_id=line.lot_id, zone=zone,
                        qty_delta=-qty, batch_id=line.lot.batch_id, line_id=line.pk,
                    ))
                else:
                    effects.stock.extend(_consume_zone_fifo(line, zone, qty))
                line.save()
            total += line.cogs_total
        doc.subtotal = total
        doc.grand_total = total
        return effects

    def check_voidable(self, doc: Document) -> None:
        if doc.related_document_id and doc.related_document.status == Document.Status.POSTED:
            raise PostingError(_("Void the stock count; its auto adjustment will void with it."))


class StockCountHandler(Handler):
    """SC: variance from frozen WAREHOUSE lot snapshot."""

    def validate(self, doc: Document) -> None:
        if not getattr(doc, "_posting_actor", doc.created_by).is_owner:
            raise PostingError(_("Only the owner can approve stock counts (D27)."))
        if not list(doc.lines.all()):
            raise PostingError(_("Stock count has no snapshot lines."))

    def build_effects(self, doc: Document) -> Effects:
        effects = Effects()
        total = Decimal("0.00")
        moved = StockLedger.objects.filter(
            at__gt=doc.created_at,
            zone=Zone.WAREHOUSE,
            item_id__in=doc.lines.values_list("item_id", flat=True),
        ).exists()
        if moved:
            log_event(doc.created_by, "STOCK_COUNT_MOVEMENT_WARNING", "Document", doc.pk,
                      {"message": "Movement happened after the count snapshot."})
        for line in doc.lines.select_related("item", "batch", "lot"):
            if line.lot_id is None:
                raise PostingError(_("Line %(item)s: snapshot line has no lot.")
                                   % {"item": line.item.code})
            counted = line.qty_entered * line.factor
            diff = counted - line.qty_base
            line.qty_delta = diff
            line.cogs_total = round2(Decimal(abs(diff)) * line.lot.unit_cost)
            line.save()
            total += line.cogs_total
        doc.subtotal = total
        doc.grand_total = total
        return effects

    def after_post(self, doc: Document, actor) -> None:
        variances = [line for line in doc.lines.select_related("item", "batch", "lot")
                     if line.qty_delta]
        if not variances:
            return
        from docs.posting import post

        adj = Document.objects.create(
            doc_type=DocType.ADJUSTMENT,
            created_by=actor,
            related_document=doc,
            notes=_("Stock count adjustment for %(no)s") % {"no": doc.doc_no},
        )
        for line in variances:
            DocumentLine.objects.create(
                document=adj,
                item=line.item,
                batch=line.batch,
                lot=line.lot if line.qty_delta < 0 else None,
                source_zone=Zone.WAREHOUSE,
                unit_label=line.unit_label,
                factor=1,
                qty_entered=abs(line.qty_delta),
                qty_delta=line.qty_delta,
                unit_cost_entered=line.lot.unit_cost,
            )
        post(adj, actor)


register(DocType.RECEIVING, ReceivingHandler())
register(DocType.SUPPLIER_RETURN, SupplierReturnHandler())
register(DocType.ZONE_MOVE, ZoneMoveHandler())
register(DocType.ADJUSTMENT, AdjustmentHandler())
register(DocType.STOCK_COUNT, StockCountHandler())
