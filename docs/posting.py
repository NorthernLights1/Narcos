"""The posting engine (§4). One code path posts every document type;
per-type logic plugs in via handlers. Build once, reuse everywhere."""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from core.audit import log_event
from core.models import CompanySettings, NumberSequence
from docs.models import DocType, Document, ImmutableDocumentError, PREFIXES
from money.models import MoneyLedger, PartyLedger, WithholdingLedger
from stock.models import StockBalance, StockLedger


class PostingError(Exception):
    """Business-rule failure during post/void. Message is user-facing."""


OPENING_TYPES = {
    DocType.OPENING_STOCK, DocType.OPENING_AR, DocType.OPENING_AP,
    DocType.OPENING_CASH, DocType.OPENING_CONSIGNMENT, DocType.OPENING_EXPIRED,
}


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

    def after_post(self, doc: Document, actor) -> None:
        """Optional hook for linked documents that need the source doc_no."""


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
            # D100: it used to print raw row ids ("item 10 lot 12"), which told
            # the owner nothing about which medicine was short.
            batch = (_(", batch %(no)s") % {"no": balance.batch.batch_no}
                     if balance.batch_id else "")
            raise PostingError(
                _("Not enough stock: %(item)s%(batch)s in %(zone)s "
                  "(have %(have)d, need %(need)d).")
                % {"item": balance.item, "batch": batch,
                   "zone": balance.get_zone_display(),
                   "have": balance.qty, "need": -net[key]}
            )
        balance.qty = new_qty
        balance.save(update_fields=["qty"])


def _check_money_stays_positive(deltas, during_void: bool) -> None:
    """D101: stock has a no-negative CHECK constraint (D4); money never did,
    so an expense could be paid from an empty drawer and a void could take an
    account below zero. Whether that is wrong is the owner's call — a business
    that does not run every birr through the books has real payments with no
    recorded income behind them. `negative_balance_policy` decides.
    """
    policy = CompanySettings.load().negative_balance_policy
    if policy == CompanySettings.NegativeBalance.ALLOW:
        return
    if policy == CompanySettings.NegativeBalance.BLOCK_VOID and not during_void:
        return
    net: dict[int, Decimal] = {}
    for account_id, delta in deltas:
        net[account_id] = net.get(account_id, Decimal("0.00")) + delta
    for account_id in sorted(net):
        delta = net[account_id]
        if delta >= 0:
            continue
        balance = MoneyLedger.objects.filter(account_id=account_id).aggregate(
            s=Sum("amount_delta"))["s"] or Decimal("0.00")
        if balance + delta >= 0:
            continue
        from catalog.models import Account  # error path only
        name = Account.objects.filter(pk=account_id).values_list(
            "name", flat=True).first() or account_id
        if during_void:
            raise PostingError(
                _("Cannot void: %(account)s would go to %(after)s. Reverse "
                  "the documents that spent it first, or allow negative "
                  "balances in Settings.")
                % {"account": name, "after": balance + delta})
        raise PostingError(
            _("Not enough money in %(account)s (have %(have)s, need "
              "%(need)s). Record the income or opening balance behind it "
              "first, or allow negative balances in Settings.")
            % {"account": name, "have": balance, "need": -delta})


def _write_money(doc: Document, effects: Effects, now) -> None:
    _check_money_stays_positive(effects.money, during_void=False)
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


# D95/D96: the document types `void()` drags down with their parent. Split in
# two on purpose — ADJUSTMENT is regenerated by `after_post` (a stock count
# rebuilds its own adjustment), so a correction puts it back. The rest are
# documents somebody typed, and nothing recreates them.
VOID_CASCADE_TYPES = (
    DocType.CUSTOMER_PAYMENT, DocType.SUPPLIER_PAYMENT, DocType.ADJUSTMENT,
    DocType.CUSTOMER_RETURN,
)
CORRECTION_UNRESTORABLE_TYPES = (
    DocType.CUSTOMER_PAYMENT, DocType.SUPPLIER_PAYMENT, DocType.CUSTOMER_RETURN,
)


# A paid cash sale and a paid receiving each generate their own settling
# payment in `after_post`, from the document's own payment lines. A correction
# copies those lines, so posting the replacement builds the payment again.
# `related_document` is not on either payment form (DOC_CONFIG), so a payment
# pointing back at one of these can only be the automatic one.
AUTO_PAYMENT_OF = {
    DocType.SALE: DocType.CUSTOMER_PAYMENT,
    DocType.RECEIVING: DocType.SUPPLIER_PAYMENT,
}


def _restorable_dependent_pks(doc: Document) -> set:
    """Documents that hang off `doc` but that a correction *does* put back.

    `doc` itself is in the set: a document never blocks its own correction.
    """
    spared = {doc.pk}
    auto_type = AUTO_PAYMENT_OF.get(doc.doc_type)
    if auto_type is not None:
        spared.update(Document.objects.filter(
            related_document=doc, doc_type=auto_type,
        ).values_list("pk", flat=True))
    return spared


def dependents_a_correction_cannot_restore(doc: Document) -> list:
    """R70: posted documents that voiding `doc` reverses and that posting a
    correction never puts back.

    A correction copies the source document's own fields, lines, charges and
    payment lines — nothing else. A linked customer return, or the receipt that
    settled this invoice, is a separate document; `void()` reverses it (D95/D96)
    and the replacement has no way to recreate it, so the returned goods and the
    customer's money would simply leave the books.
    """
    # The two queries are merged in Python: the allocation join makes them
    # impossible for the ORM to OR together.
    spared = _restorable_dependent_pks(doc)
    linked = Document.objects.filter(
        related_document=doc,
        status=Document.Status.POSTED,
        doc_type__in=CORRECTION_UNRESTORABLE_TYPES,
    ).exclude(pk__in=spared)
    settling = Document.objects.filter(
        allocations_made__target=doc,
        status=Document.Status.POSTED,
    ).exclude(pk__in=spared)
    found = {d.pk: d for d in linked}
    found.update({d.pk: d for d in settling})
    return [found[pk] for pk in sorted(found)]


# Doc types whose lines are copied into a fresh draft AND whose `qty_base`
# means "qty_entered (+ free_qty) in base units". Everything else writes
# qty_base from something else entirely — a stock count freezes the pre-count
# snapshot, a settlement stores sold+returned+expired, an adjustment stores
# |qty_delta| — so the pack-scale marker is meaningless for them and would
# refuse perfectly good corrections.
PACK_SCALE_CHECKED_TYPES = (
    DocType.RECEIVING, DocType.SALE, DocType.PROFORMA,
    DocType.CONSIGNMENT_ISSUE, DocType.CUSTOMER_RETURN, DocType.SUPPLIER_RETURN,
    DocType.ZONE_MOVE, DocType.OPENING_STOCK, DocType.OPENING_CONSIGNMENT,
    DocType.OPENING_EXPIRED,
)


def lines_posted_on_a_pack_scale(doc: Document) -> list:
    """D122: lines posted before unit conversion was removed.

    Until D122 a line could be typed in packs and stored in base units as
    `qty_entered x factor`. The multiplier is gone, so copying such a line into
    a fresh draft would re-post `qty_entered` alone and register a different
    quantity than the original moved. `qty_base != qty_entered + free_qty`
    identifies those rows without needing the dropped column.

    Deliberately NOT gated on `qty_base` being non-zero: a historical
    `factor = 0` row (reachable by a crafted POST before D120 closed it) stored
    qty_base 0 against a positive qty_entered, and re-posting it would register
    stock the original never moved. That is exactly a row we must refuse.
    """
    if doc.doc_type not in PACK_SCALE_CHECKED_TYPES:
        return []
    return [
        line for line in doc.lines.select_related("item")
        if line.qty_base != line.qty_entered + line.free_qty
    ]


def _refuse_a_pack_scaled_copy(doc: Document, what: str) -> None:
    legacy = lines_posted_on_a_pack_scale(doc)
    if not legacy:
        return
    raise PostingError(_(
        "%(no)s was entered on a pack scale, before unit conversion was "
        "removed (%(items)s). %(what)s would re-post it in base units and "
        "register a different quantity than the original moved. Void %(no)s "
        "and enter a new document instead."
    ) % {"no": doc.doc_no, "what": what,
         "items": ", ".join(sorted({ln.item.code for ln in legacy}))})


def check_correctable(doc: Document) -> None:
    """R70: refuse a correction that would silently delete linked documents."""
    blockers = dependents_a_correction_cannot_restore(doc)
    if blockers:
        raise PostingError(_(
            "%(no)s cannot be corrected: %(list)s would be reversed with it and "
            "nothing brings them back. Void those first, then correct %(no)s."
        ) % {"no": doc.doc_no, "list": ", ".join(d.doc_no for d in blockers)})
    _refuse_a_pack_scaled_copy(doc, _("Correcting it"))


def _void_the_document_being_corrected(draft: Document, actor) -> None:
    """D92: reverse the document this draft replaces, before the draft posts.

    Correcting is owner-only, and `void()` enforces that too — but it would
    complain about voiding, which is not the button anyone pressed. Say what
    is actually happening instead.
    """
    if not actor.is_owner:
        raise PostingError(_("Only the owner can post a correction (D28)."))
    # R70: take the original's row lock *before* looking for dependents. A
    # return or receipt posting concurrently locks the same row (D14), so
    # holding it first means the dependent list cannot grow between the check
    # and the void it is guarding.
    original = Document.objects.select_for_update().get(pk=draft.corrects_id)
    if original.status != Document.Status.POSTED:
        raise PostingError(_(
            "%(no)s is no longer posted, so this correction cannot replace "
            "it. Post it as a new document instead."
        ) % {"no": original.doc_no})
    check_correctable(original)  # R70 — binding check, inside the transaction
    void(original, actor, draft.correction_reason)


def post(document: Document, actor, override_reason: str = "") -> Document:
    """§4 Post(): single transaction, serialized by row locks (D14).
    override_reason: owner-only escape for credit BLOCK (D25) — never for
    negative stock (D4). Audited when used."""
    if override_reason and not actor.is_owner:
        raise PostingError(_("Only the owner can override (D28)."))
    with transaction.atomic():
        try:
            doc = Document.objects.select_for_update().get(pk=document.pk)
        except Document.DoesNotExist:
            raise PostingError(_("Document no longer exists (draft was deleted)."))
        if doc.status != Document.Status.DRAFT:
            raise PostingError(_("Only drafts can be posted (D28)."))
        # D92: a correction voids what it replaces *first*, here, inside this
        # same transaction — so the goods and money the original held are
        # free before this document's own checks run, and a failure in
        # either half rolls back both. Until this moment the original is
        # untouched, which is what makes abandoning a correction harmless.
        if doc.corrects_id:
            _void_the_document_being_corrected(doc, actor)
        doc._override_reason = override_reason  # read by handlers (credit check)
        doc._posting_actor = actor  # read by owner-only handlers
        handler = get_handler(doc.doc_type)
        handler.validate(doc)

        number = NumberSequence.take(doc.doc_type)  # locks the sequence row (D8/D14)
        effects = handler.build_effects(doc)

        now = timezone.now()
        _check_clock_anomaly(now, actor)
        _apply_stock(doc, effects.stock, now, actor)
        _write_money(doc, effects, now)

        doc.doc_no = f"{PREFIXES[doc.doc_type]}-{number:06d}"
        if doc.doc_type not in OPENING_TYPES or doc.document_date is None:
            doc.document_date = now  # D38: system time, except opening docs
        doc.status = Document.Status.POSTED
        doc.posted_by = actor
        doc.posted_at = now
        doc.save()
        log_event(actor, "POST", "Document", doc.pk,
                  {"doc_no": doc.doc_no, "doc_type": doc.doc_type})
        if override_reason:
            log_event(actor, "OVERRIDE", "Document", doc.pk,
                      {"doc_no": doc.doc_no, "reason": override_reason})
        handler.after_post(doc, actor)
    return doc


def _check_withholding_not_already_remitted(doc: Document) -> None:
    """D99: stock cannot go negative — a CHECK constraint says so. The
    withholding buckets have no such backstop, so reversing a payment whose
    withheld tax had already been remitted pushed PAYABLE below zero:
    measured at −30.00, with the 30.00 sitting at the tax office and the
    books claiming the tax office owed it back. Refuse, and name the
    remittance that has to be reversed first."""
    written = (doc.withholding_rows.filter(is_reversal=False)
               .values("direction").annotate(total=Sum("amount_delta")))
    for row in written:
        # A negative row means this document *consumed* the bucket (a
        # remittance); reversing it refills, so it can never go short.
        if row["total"] <= 0:
            continue
        balance = WithholdingLedger.objects.filter(
            direction=row["direction"]
        ).aggregate(s=Sum("amount_delta"))["s"] or Decimal("0.00")
        if balance - row["total"] >= 0:
            continue
        remittance = Document.objects.filter(
            doc_type=DocType.WHT_REMITTANCE, status=Document.Status.POSTED,
        ).order_by("-pk").first()
        raise PostingError(
            _("Cannot void: the %(amount)s withheld here was already paid to "
              "the tax office by %(remittance)s. Void that remittance first — "
              "the amount goes back into what you owe the tax office — then "
              "this document can be voided.")
            % {"amount": row["total"],
               "remittance": remittance.doc_no if remittance else _("a remittance")}
        )


def _check_period_is_open(doc: Document) -> None:
    """R71: voiding rewrites the month the document was in, not the month it
    is being voided in.

    The reversal rows are stamped now, but the document flips to VOIDED and
    the reports only ever show currently-posted documents — so a June sale
    voided in August disappears out of June and turns up in no other month.
    A June report printed and filed in July silently stops matching.

    Until reports can show a reversal at its own date, the owner draws a line
    under a month by setting `books_closed_through`, and nothing on or before
    it can move. Left empty (the default), nothing changes.
    """
    from core.models import CompanySettings

    closed_through = CompanySettings.load().books_closed_through
    if closed_through is None or doc.document_date is None:
        return
    day = timezone.localtime(doc.document_date).date()
    if day <= closed_through:
        raise PostingError(_(
            "%(no)s is dated %(day)s, and the books are closed through "
            "%(closed)s. Voiding it would change a month that has already "
            "been reported. Enter a correcting document dated today instead."
        ) % {"no": doc.doc_no, "day": day, "closed": closed_through})


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
        _check_period_is_open(doc)                     # R71
        get_handler(doc.doc_type).check_voidable(doc)  # D5 hook
        _check_withholding_not_already_remitted(doc)   # D99

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
        money_reversals = [(row.account_id, -row.amount_delta)
                           for row in doc.money_rows.filter(is_reversal=False)]
        _check_money_stays_positive(money_reversals, during_void=True)  # D101
        for account_id, delta in money_reversals:
            MoneyLedger.objects.create(account_id=account_id,
                                       amount_delta=delta,
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
        for linked in Document.objects.filter(
            related_document=doc,
            status=Document.Status.POSTED,
            # D96: a customer return hands goods back *against this sale*.
            # Leaving it posted while the sale is reversed credited the customer
            # for a sale that no longer existed and put the returned packs in the
            # warehouse twice — stock the business never had. It goes back with
            # the sale it belongs to. R70 reads the same tuple, so the cascade
            # and the correction guard cannot drift apart.
            doc_type__in=VOID_CASCADE_TYPES,
        ).order_by("pk"):
            void(linked, actor, reason)

        # D95: a payment that settled this document is a *separate* document,
        # so nothing above touches it — reversing the invoice alone left the
        # party owing nothing and the business owing them what they had paid,
        # with the allocation pointing at a document that no longer exists.
        # The receipt goes back with the invoice it settled. D94 guarantees it
        # settled only this one, so no other invoice is disturbed.
        settled_by = Document.objects.filter(
            allocations_made__target=doc,
            status=Document.Status.POSTED,
        ).distinct().order_by("pk")
        for payment in settled_by:
            void(payment, actor, _("%(reason)s (settled %(no)s)") % {
                "reason": reason, "no": doc.doc_no,
            })
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
