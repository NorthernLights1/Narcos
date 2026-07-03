"""Opening-balance handlers (P8)."""

from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext as _

from docs.models import DocType, Document, LotConsumption
from docs.posting import Effects, Handler, PostingError, StockDelta, register
from stock.models import Batch, CostLot, Zone


class OpeningStockBase(Handler):
    zone = Zone.WAREHOUSE
    needs_customer = False

    def validate(self, doc: Document) -> None:
        if not getattr(doc, "_posting_actor", doc.created_by).is_owner:
            raise PostingError(_("Only the owner can post opening balances."))
        if self.needs_customer and doc.customer_id is None:
            raise PostingError(_("Opening consignment needs a customer."))
        lines = list(doc.lines.select_related("item"))
        if not lines:
            raise PostingError(_("Opening stock needs at least one line."))
        for line in lines:
            if line.qty_entered <= 0:
                raise PostingError(_("Line %(item)s: quantity must be positive.")
                                   % {"item": line.item.code})
            if line.unit_cost_entered is None or line.unit_cost_entered < 0:
                raise PostingError(_("Line %(item)s: unit cost is required.")
                                   % {"item": line.item.code})
            if self.needs_customer and line.unit_price < 0:
                raise PostingError(_("Line %(item)s: locked price cannot be negative.")
                                   % {"item": line.item.code})
            if line.item.is_batch_tracked:
                if not line.batch_no_entered.strip():
                    raise PostingError(_("Line %(item)s: batch number required.")
                                       % {"item": line.item.code})
                if line.item.has_expiry and line.expiry_entered is None:
                    raise PostingError(_("Line %(item)s: expiry date required.")
                                       % {"item": line.item.code})
            elif line.batch_no_entered or line.expiry_entered:
                raise PostingError(_("Line %(item)s: item is not batch tracked.")
                                   % {"item": line.item.code})

    def build_effects(self, doc: Document) -> Effects:
        now = timezone.now()
        effects = Effects()
        total = Decimal("0.00")
        for line in doc.lines.select_related("item"):
            batch = None
            if line.item.is_batch_tracked:
                batch, created = Batch.objects.get_or_create(
                    item=line.item, batch_no=line.batch_no_entered.strip(),
                    defaults={"expiry_date": line.expiry_entered},
                )
                if not created and batch.expiry_date != line.expiry_entered:
                    raise PostingError(
                        _("Batch %(no)s of %(item)s already exists with expiry %(old)s.")
                        % {"no": batch.batch_no, "item": line.item.code,
                           "old": batch.expiry_date}
                    )
            qty = line.qty_entered * line.factor
            lot = CostLot.objects.create(
                item=line.item, batch=batch, source_line=line,
                received_at=now, qty_received=qty, unit_cost=line.unit_cost_entered,
            )
            line.batch = batch
            line.qty_base = qty
            line.line_net = Decimal(line.qty_entered) * line.unit_price
            line.cogs_total = Decimal(qty) * line.unit_cost_entered
            line.save()
            zone = line.target_zone or self.zone
            if zone == Zone.CONSIGNED:
                LotConsumption.objects.create(line=line, lot=lot, qty=qty,
                                              unit_cost=line.unit_cost_entered)
            effects.stock.append(StockDelta(
                item_id=line.item_id, lot_id=lot.pk, zone=zone,
                qty_delta=qty, batch_id=batch.pk if batch else None,
                customer_id=doc.customer_id if zone == Zone.CONSIGNED else None,
                line_id=line.pk,
            ))
            total += line.cogs_total
        doc.subtotal = total
        doc.grand_total = total
        return effects


class OpeningStockHandler(OpeningStockBase):
    zone = Zone.WAREHOUSE


class OpeningExpiredHandler(OpeningStockBase):
    zone = Zone.EXPIRED

    def validate(self, doc: Document) -> None:
        super().validate(doc)
        for line in doc.lines.all():
            if line.target_zone and line.target_zone not in (Zone.EXPIRED, Zone.UNFIT):
                raise PostingError(_("Opening expired/unfit rows must target EXPIRED or UNFIT."))


class OpeningConsignmentHandler(OpeningStockBase):
    zone = Zone.CONSIGNED
    needs_customer = True

    def build_effects(self, doc: Document) -> Effects:
        effects = super().build_effects(doc)
        doc.subtotal = sum((line.line_net for line in doc.lines.all()), Decimal("0.00"))
        doc.grand_total = doc.subtotal
        return effects


class OpeningPartyHandler(Handler):
    party_type = ""

    def validate(self, doc: Document) -> None:
        if not getattr(doc, "_posting_actor", doc.created_by).is_owner:
            raise PostingError(_("Only the owner can post opening balances."))
        if self.party_type == "CUSTOMER" and doc.customer_id is None:
            raise PostingError(_("Opening AR needs a customer."))
        if self.party_type == "SUPPLIER" and doc.supplier_id is None:
            raise PostingError(_("Opening AP needs a supplier."))
        if doc.grand_total <= 0:
            raise PostingError(_("Opening balance amount must be positive."))

    def build_effects(self, doc: Document) -> Effects:
        party_id = doc.customer_id if self.party_type == "CUSTOMER" else doc.supplier_id
        return Effects(party=[(self.party_type, party_id, doc.grand_total)])


class OpeningARHandler(OpeningPartyHandler):
    party_type = "CUSTOMER"


class OpeningAPHandler(OpeningPartyHandler):
    party_type = "SUPPLIER"


class OpeningCashHandler(Handler):
    def validate(self, doc: Document) -> None:
        if not getattr(doc, "_posting_actor", doc.created_by).is_owner:
            raise PostingError(_("Only the owner can post opening balances."))
        lines = list(doc.payment_lines.all())
        if not lines:
            raise PostingError(_("Opening cash needs at least one account line."))
        if any(line.amount <= 0 for line in lines):
            raise PostingError(_("Every opening cash line must be positive."))

    def build_effects(self, doc: Document) -> Effects:
        effects = Effects()
        total = Decimal("0.00")
        for line in doc.payment_lines.all():
            effects.money.append((line.account_id, line.amount))
            total += line.amount
        doc.grand_total = total
        doc.subtotal = total
        return effects


register(DocType.OPENING_STOCK, OpeningStockHandler())
register(DocType.OPENING_EXPIRED, OpeningExpiredHandler())
register(DocType.OPENING_CONSIGNMENT, OpeningConsignmentHandler())
register(DocType.OPENING_AR, OpeningARHandler())
register(DocType.OPENING_AP, OpeningAPHandler())
register(DocType.OPENING_CASH, OpeningCashHandler())
