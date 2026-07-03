"""The posting engine (§4). One code path posts every document type;
per-type logic plugs in via handlers. Build once, reuse everywhere."""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext as _

from core.audit import log_event
from core.models import NumberSequence
from docs.models import DocType, Document, ImmutableDocumentError, PREFIXES
from money.models import MoneyLedger, PartyLedger, WithholdingLedger
from stock.models import StockBalance, StockLedger


class PostingError(Exception):
    """Business-rule failure during post/void. Message is user-facing."""


@dataclass(frozen=True)
class StockDelta:
    item_id: int
    lot_id: int
    zone: str
    qty_delta: int
    batch_id: int | None = None
    customer_id: int | None = None
    line_id: int | None = None

    @property
    def balance_key(self) -> tuple:
        return (self.item_id, self.lot_id, self.zone,
                self.batch_id or 0, self.customer_id or 0)


@dataclass
class Effects:
    stock: list[StockDelta] = field(default_factory=list)
    money: list[tuple[int, Decimal]] = field(default_factory=list)  # (account_id, delta)
    party: list[tuple[str, int, Decimal]] = field(default_factory=list)
    withholding: list[tuple[str, Decimal, str]] = field(default_factory=list)


class Handler:
    """Per-doc-type plug-in. validate() runs before locks; build_effects()
    runs under lock and may also freeze ※ snapshots onto the document/lines."""

    def validate(self, doc: Document) -> None:  # raise PostingError
        raise NotImplementedError

    def build_effects(self, doc: Document) -> Effects:
        raise NotImplementedError

    def check_voidable(self, doc: Document) -> None:
        """Raise PostingError to block voiding (e.g. D5). Default: allowed."""


_HANDLERS: dict[str, Handler] = {}


def register(doc_type: str, handler: Handler) -> None:
    _HANDLERS[doc_type] = handler


def get_handler(doc_type: str) -> Handler:
    try:
        return _HANDLERS[doc_type]
    except KeyError:
        raise PostingError(_("No handler for document type %s") % doc_type)


def _check_clock_anomaly(now, actor) -> None:
    """D47/I6: if the clock went backwards relative to the last posting, audit it."""
    latest = Document.objects.filter(posted_at__isnull=False).aggregate(
        m=Max("posted_at")
    )["m"]
    if latest is not None and now < latest:
        log_event(actor, "CLOCK_ANOMALY", "Document",
                  detail={"now": now.isoformat(), "latest_posting": latest.isoformat()})


def _apply_stock(doc: Document, deltas: list[StockDelta], now, actor,
                 is_reversal: bool = False) -> None:
    if not deltas:
        return
    for d in deltas:
        StockLedger.objects.create(
            document=doc, document_line_id=d.line_id, item_id=d.item_id,
            batch_id=d.batch_id, lot_id=d.lot_id, zone=d.zone,
            consignment_customer_id=d.customer_id, qty_delta=d.qty_delta,
            is_reversal=is_reversal, at=now,
        )
    # Net the deltas per balance row, then lock/update in stable key order (D14)
    net: dict[tuple, int] = {}
    sample: dict[tuple, StockDelta] = {}
    for d in deltas:
        net[d.balance_key] = net.get(d.balance_key, 0) + d.qty_delta
        sample[d.balance_key] = d
    for key in sorted(net):
        d = sample[key]
        balance, _created = StockBalance.objects.select_for_update().get_or_create(
            item_id=d.item_id, lot_id=d.lot_id, zone=d.zone,
            batch_id=d.batch_id, consignment_customer_id=d.customer_id,
            defaults={"qty": 0},
        )
        new_qty = balance.qty + net[key]
        if new_qty < 0:
            # D4: no negative stock, ever. The DB CHECK is the backstop; this
            # check gives the user a readable message. No override — the fix
            # path is an owner adjustment first (D28).
            raise PostingError(
                _("Not enough stock: item %(item)s lot %(lot)s in %(zone)s "
                  "(have %(have)d, need %(need)d).")
                % {"item": d.item_id, "lot": d.lot_id, "zone": d.zone,
                   "have": balance.qty, "need": -net[key]}
            )
        balance.qty = new_qty
        balance.save(update_fields=["qty"])


def _write_money(doc: Document, effects: Effects, now) -> None:
    for account_id, delta in effects.money:
        MoneyLedger.objects.create(
            account_id=account_id, amount_delta=delta, document=doc, at=now
        )
    for party_type, party_id, delta in effects.party:
        PartyLedger.objects.create(
            party_type=party_type, party_id=party_id, amount_delta=delta,
            document=doc, at=now,
        )
    for direction, delta, certificate_no in effects.withholding:
        WithholdingLedger.objects.create(
            direction=direction, amount_delta=delta, document=doc,
            certificate_no=certificate_no, at=now,
        )


def post(document: Document, actor) -> Document:
    """§4 Post(): single transaction, serialized by row locks (D14)."""
    with transaction.atomic():
        try:
            doc = Document.objects.select_for_update().get(pk=document.pk)
        except Document.DoesNotExist:
            raise PostingError(_("Document no longer exists (draft was deleted)."))
        if doc.status != Document.Status.DRAFT:
            raise PostingError(_("Only drafts can be posted (D28)."))
        handler = get_handler(doc.doc_type)
        handler.validate(doc)

        number = NumberSequence.take(doc.doc_type)  # locks the sequence row (D8/D14)
        effects = handler.build_effects(doc)

        now = timezone.now()
        _check_clock_anomaly(now, actor)
        _apply_stock(doc, effects.stock, now, actor)
        _write_money(doc, effects, now)

        doc.doc_no = f"{PREFIXES[doc.doc_type]}-{number:06d}"
        doc.document_date = now  # D38: system time, never user-chosen
        doc.status = Document.Status.POSTED
        doc.posted_by = actor
        doc.posted_at = now
        doc.save()
        log_event(actor, "POST", "Document", doc.pk,
                  {"doc_no": doc.doc_no, "doc_type": doc.doc_type})
    return doc


def void(document: Document, actor, reason: str) -> Document:
    """§4 Void(): owner only, exact reversal, same balance checks (D4/D28)."""
    if not actor.is_owner:
        raise PostingError(_("Only the owner can void documents (D28)."))
    if not reason.strip():
        raise PostingError(_("A void reason is required (D28)."))
    with transaction.atomic():
        try:
            doc = Document.objects.select_for_update().get(pk=document.pk)
        except Document.DoesNotExist:
            raise PostingError(_("Document no longer exists."))
        if doc.status != Document.Status.POSTED:
            raise PostingError(_("Only posted documents can be voided."))
        get_handler(doc.doc_type).check_voidable(doc)  # D5 hook

        now = timezone.now()
        # Reverse stock: negate every ledger row this document wrote
        reversals = [
            StockDelta(
                item_id=row.item_id, lot_id=row.lot_id, zone=row.zone,
                batch_id=row.batch_id, customer_id=row.consignment_customer_id,
                qty_delta=-row.qty_delta, line_id=row.document_line_id,
            )
            for row in doc.stock_moves.filter(is_reversal=False)
        ]
        _apply_stock(doc, reversals, now, actor, is_reversal=True)
        for row in list(doc.money_rows.filter(is_reversal=False)):
            MoneyLedger.objects.create(account_id=row.account_id,
                                       amount_delta=-row.amount_delta,
                                       document=doc, is_reversal=True, at=now)
        for row in list(doc.party_rows.filter(is_reversal=False)):
            PartyLedger.objects.create(party_type=row.party_type, party_id=row.party_id,
                                       amount_delta=-row.amount_delta,
                                       document=doc, is_reversal=True, at=now)
        for row in list(doc.withholding_rows.filter(is_reversal=False)):
            WithholdingLedger.objects.create(direction=row.direction,
                                             amount_delta=-row.amount_delta,
                                             document=doc, certificate_no=row.certificate_no,
                                             is_reversal=True, at=now)

        doc.status = Document.Status.VOIDED
        doc.voided_by = actor
        doc.voided_at = now
        doc.void_reason = reason
        doc.save()
        log_event(actor, "VOID", "Document", doc.pk,
                  {"doc_no": doc.doc_no, "reason": reason})
    return doc


# --- The two simplest handlers prove the engine (§16 P2) ---


class ExpenseHandler(Handler):
    """§7.9: category, account (via payment lines), payee, amount → money −."""

    @staticmethod
    def _check_lines(doc: Document) -> list:
        lines = list(doc.payment_lines.all())
        if not lines:
            raise PostingError(_("Expense needs at least one payment line."))
        if any(line.amount <= 0 for line in lines):
            raise PostingError(_("Every payment line must be positive."))
        total = sum((line.amount for line in lines), Decimal("0.00"))
        if doc.grand_total != total:
            raise PostingError(_("Grand total must equal the sum of payment lines."))
        return lines

    def validate(self, doc: Document) -> None:
        if doc.expense_category_id is None:
            raise PostingError(_("Expense needs a category."))
        self._check_lines(doc)

    def build_effects(self, doc: Document) -> Effects:
        # Re-read and re-check under the posting lock: a line inserted between
        # validate() and here must not slip into the ledger unverified (TOCTOU).
        effects = Effects()
        for line in self._check_lines(doc):
            effects.money.append((line.account_id, -line.amount))
        return effects


class TransferHandler(Handler):
    """§7.9/D9: from-account, to-account, amount → two money rows."""

    def validate(self, doc: Document) -> None:
        if doc.from_account_id is None or doc.to_account_id is None:
            raise PostingError(_("Transfer needs both accounts (D9)."))
        if doc.from_account_id == doc.to_account_id:
            raise PostingError(_("Transfer accounts must differ."))
        if doc.grand_total <= 0:
            raise PostingError(_("Transfer amount must be positive."))

    def build_effects(self, doc: Document) -> Effects:
        return Effects(money=[
            (doc.from_account_id, -doc.grand_total),
            (doc.to_account_id, doc.grand_total),
        ])


register(DocType.EXPENSE, ExpenseHandler())
register(DocType.TRANSFER, TransferHandler())
