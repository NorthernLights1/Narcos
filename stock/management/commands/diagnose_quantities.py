"""Read-only quantity diagnostic (support tool).

Answers the field reports without touching a single row:

  1. "I entered 180 and the system registered a different number."
  2. "After a sale, more stock is left than I expected."

and, since D122 removed unit conversion, finds the rows that were posted on a
pack scale while `factor` still existed — the ones that need regularizing.

Every database statement below is a SELECT: the command never inserts, updates
or deletes a row, so it is safe to run against live client data at any time.
(`--export` does write one JSON file to the path you name — that is its whole
purpose; nothing else touches the disk.) It works both before and after the
D122 migration: the legacy marker is `qty_base != qty_entered + free_qty`,
which needs no `factor` column.

    docker compose exec web python manage.py diagnose_quantities
    docker compose exec web python manage.py diagnose_quantities --item AMOX-500
    docker compose exec web python manage.py diagnose_quantities --export out.json
"""

import json

from django.core.management.base import BaseCommand
from django.db.models import Sum

from core.models import CompanySettings
from docs.models import Document, DocumentLine, DocType
from docs.posting import PACK_SCALE_CHECKED_TYPES
from stock.models import StockBalance, StockLedger

BAR = "=" * 78
RULE = "-" * 78

STOCK_IN_TYPES = (DocType.RECEIVING, DocType.OPENING_STOCK)
STOCK_OUT_TYPES = (DocType.SALE, DocType.CONSIGNMENT_ISSUE)


def is_pack_scaled(line) -> bool:
    """D122: posted in packs, stored in base units.

    One definition of "legacy row", shared with the posting guard: same doc-type
    scope, same comparison. A stock count, settlement or adjustment writes
    `qty_base` from something other than the typed quantity, so including them
    here would report healthy rows as damaged.
    """
    return (line.document.doc_type in PACK_SCALE_CHECKED_TYPES
            and line.qty_base != line.qty_entered + line.free_qty)


class Command(BaseCommand):
    help = "Read-only: explain every difference between entered and registered quantity."

    def add_arguments(self, parser):
        parser.add_argument("--item", help="Limit the report to one item code.")
        parser.add_argument("--export", metavar="PATH",
                            help="Also write the findings as JSON for offline analysis.")

    # ---------- helpers ----------

    def _posted_lines(self, item_code=None):
        # Every posted line, deliberately unfiltered by doc type: `factor` used
        # to sit on ten different line configs, so a doc-type allowlist here
        # would silently miss PROFORMA, ZONE_MOVE and the OPENING_* types.
        qs = (DocumentLine.objects
              .filter(document__status=Document.Status.POSTED)
              .select_related("document", "item", "batch")
              .order_by("document__doc_type", "document__doc_no", "pk"))
        if item_code:
            qs = qs.filter(item__code=item_code)
        return qs

    def _head(self, title):
        self.stdout.write("")
        self.stdout.write(BAR)
        self.stdout.write(title)
        self.stdout.write(BAR)

    def _ok(self, message):
        self.stdout.write(self.style.SUCCESS("  OK  " + message))

    def _flag(self, message):
        self.stdout.write(self.style.WARNING("  >>  " + message))

    # ---------- checks ----------

    def check_drafts_with_a_multiplier(self):
        """CHECK 0b — the D122 pre-flight. Run this BEFORE the migration.

        Queries the DATABASE COLUMN, not the model. The whole point of this
        check is to run from the new image against a database that has not
        been migrated yet — and in the new code `DocumentLine` no longer has a
        `factor` field at all, so asking the model would always answer "gone"
        and the pre-flight would silently pass. The old image does not carry
        this command, so the model route cannot work in either direction.

        To use it properly, start the container with NARCOS_AUTO_MIGRATE=0 so
        the entrypoint does not migrate before you have looked.
        """
        from django.db import connection

        self._head("CHECK 0b  Drafts still carrying a pack multiplier (D122 pre-flight)")
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'docs_documentline' AND column_name = 'factor'
            """)
            if cursor.fetchone() is None:
                self._ok("the factor column is already gone from this database "
                         "— the D122 migration has already run here.")
                return
            cursor.execute("""
                SELECT d.id, d.doc_type, i.code, l.qty_entered, l.free_qty,
                       l.factor, l.unit_label
                FROM docs_documentline l
                JOIN docs_document d ON d.id = l.document_id
                JOIN catalog_item i ON i.id = l.item_id
                WHERE d.status = 'DRAFT' AND l.factor <> 1
                ORDER BY d.id, l.id
            """)
            rows = cursor.fetchall()

        if not rows:
            self._ok("no unposted draft carries a factor other than 1. "
                     "The D122 migration will quarantine nothing.")
            return
        for doc_id, doc_type, code, qty, free, factor, label in rows:
            self._flag(f"draft #{doc_id} ({doc_type}) {code}: {qty}"
                       + (f"+{free} free" if free else "")
                       + f" x{factor} {label or ''} — will be CLEARED to 0 and "
                         "must be re-entered by hand")
        self._flag(f"{len(rows)} draft line(s) will be quarantined by D122. "
                   "Post or discard these drafts first if you would rather keep them.")

    def check_settings(self):
        self._head("CHECK 0  Entry-form switches on this installation")
        # NOT CompanySettings.load(): its get_or_create would INSERT a row,
        # and this command advertises itself as writing nothing.
        settings = CompanySettings.objects.filter(pk=1).first() or CompanySettings()
        for name in ("discounts_enabled", "fiscal_machine_present",
                     "sale_price_editable"):
            self.stdout.write(f"  {name:<24}: {getattr(settings, name)}")
        has_factor = any(f.name == "factor" for f in DocumentLine._meta.get_fields())
        self.stdout.write(f"  {'unit conversion column':<24}: "
                          f"{'STILL PRESENT (pre-D122)' if has_factor else 'removed (D122)'}")

    def check_pack_scaled(self, lines):
        """CHECK 1 — the direct answer to report #1, and the regularization list."""
        self._head("CHECK 1  Lines whose REGISTERED quantity differs from what was TYPED")
        self.stdout.write(
            "  Stock moves in base units. A row here moved a different number of\n"
            "  base units than the quantity typed on it.\n")
        rows = [ln for ln in lines if is_pack_scaled(ln)]
        if not rows:
            self._ok("every posted line registered exactly the quantity typed "
                     "(bonus goods aside). Nothing to regularize.")
            return []
        self.stdout.write(
            f"  {'Document':<14}{'Type':<20}{'Item':<16}"
            f"{'typed':>7}{'unit':>10}{'free':>6}{'REGISTERED':>12}{'implied':>9}")
        self.stdout.write("  " + RULE)
        for ln in rows:
            typed = ln.qty_entered + ln.free_qty
            implied = (ln.qty_base / typed) if typed else 0
            self.stdout.write(
                f"  {str(ln.document.doc_no or ln.document_id):<14}"
                f"{ln.document.doc_type:<20}{ln.item.code:<16}"
                f"{ln.qty_entered:>7}{(ln.unit_label or '')[:9]:>10}"
                f"{ln.free_qty:>6}{ln.qty_base:>12}{implied:>9.2f}")
        self._flag(f"{len(rows)} line(s) posted on a pack scale. "
                   "These are what the D122 correction guard refuses to copy.")
        return rows

    def check_free_quantity(self, lines):
        self._head("CHECK 2  Bonus (free) units")
        rows = [ln for ln in lines if ln.free_qty]
        if not rows:
            self._ok("no posted line carries bonus units.")
            return []
        for ln in rows:
            self._flag(f"{ln.document.doc_no} {ln.item.code}: typed {ln.qty_entered} "
                       f"+ {ln.free_qty} free = {ln.qty_base} registered")
        return rows

    def check_ledger_matches_balance(self, item_code=None):
        """CHECK 3 — is the fast balance cache still equal to the ledger truth?"""
        self._head("CHECK 3  Balance cache vs the append-only ledger (the real truth)")
        # Filter BEFORE grouping — a .filter() after .annotate() becomes a
        # HAVING clause and would silently change the grouping.
        led_qs = StockLedger.objects.all()
        bal_qs = StockBalance.objects.all()
        if item_code:
            led_qs = led_qs.filter(item__code=item_code)
            bal_qs = bal_qs.filter(item__code=item_code)
        group = ("item_id", "lot_id", "zone", "batch_id", "consignment_customer_id")
        ledger_map = {tuple(r[k] for k in group): r["total"] or 0
                      for r in led_qs.values(*group).annotate(total=Sum("qty_delta"))}
        balance_map = {tuple(r[k] for k in group): r["total"] or 0
                       for r in bal_qs.values(*group).annotate(total=Sum("qty"))}
        drift = []
        for key in set(ledger_map) | set(balance_map):
            a, b = ledger_map.get(key, 0), balance_map.get(key, 0)
            if a != b:
                drift.append({"item_id": key[0], "lot_id": key[1], "zone": key[2],
                              "ledger": a, "balance": b})
        if not drift:
            self._ok(f"all {len(balance_map)} balance rows equal the sum of their "
                     "ledger moves.")
            return []
        for d in drift:
            self._flag(f"item={d['item_id']} lot={d['lot_id']} zone={d['zone']}: "
                       f"ledger says {d['ledger']}, balance cache says {d['balance']}")
        self._flag("The displayed quantity is NOT what the movement history adds up to. "
                   "This is the signature of a hand-edited database.")
        return drift

    def check_hand_corrections(self, item_code=None):
        self._head("CHECK 4  Adjustments, counts and zone moves (stock moved without a sale)")
        qs = (Document.objects
              .filter(status=Document.Status.POSTED,
                      doc_type__in=(DocType.ADJUSTMENT, DocType.STOCK_COUNT,
                                    DocType.ZONE_MOVE))
              .select_related("posted_by").order_by("-posted_at"))
        if item_code:
            qs = qs.filter(lines__item__code=item_code).distinct()
        rows = list(qs[:40])
        if not rows:
            self._ok("no adjustment, stock count or zone move has been posted.")
            return
        for doc in rows:
            who = doc.posted_by.username if doc.posted_by else "?"
            when = doc.posted_at.strftime("%Y-%m-%d %H:%M") if doc.posted_at else "?"
            self.stdout.write(f"  {doc.doc_no:<12}{doc.doc_type:<14}{when:<18}{who:<12}"
                              f"{(doc.notes or '')[:30]}")
            for ln in doc.lines.select_related("item"):
                self.stdout.write(
                    f"      {ln.item.code:<16}qty_delta "
                    f"{format(ln.qty_delta, '+d'):>8}   qty_base {ln.qty_base:>8}")

    def check_item_history(self, item_code):
        self._head(f"CHECK 5  Every stock movement for {item_code}, oldest first")
        moves = (StockLedger.objects.filter(item__code=item_code)
                 .select_related("document", "batch").order_by("at", "pk"))
        running = 0
        self.stdout.write(f"  {'When':<18}{'Document':<14}{'Zone':<12}"
                          f"{'Move':>9}{'Running':>10}  note")
        self.stdout.write("  " + RULE)
        for mv in moves:
            running += mv.qty_delta
            self.stdout.write(
                f"  {mv.at.strftime('%Y-%m-%d %H:%M'):<18}"
                f"{str(mv.document.doc_no or '-'):<14}{mv.zone:<12}"
                f"{format(mv.qty_delta, '+d'):>9}{running:>10}  "
                f"{'REVERSAL' if mv.is_reversal else ''}")
        self.stdout.write("  " + RULE)
        self.stdout.write(f"  Ledger total across all zones: {running}")

    # ---------- entry point ----------

    def handle(self, *args, **options):
        item_code = options.get("item")
        self.stdout.write(BAR)
        self.stdout.write("NARCOS QUANTITY DIAGNOSTIC — read-only: changes no data")
        if item_code:
            self.stdout.write(f"Item filter: {item_code}")
        self.stdout.write(BAR)

        lines = list(self._posted_lines(item_code))
        self.stdout.write(f"\nPosted document lines examined: {len(lines)}")

        self.check_settings()
        self.check_drafts_with_a_multiplier()
        scaled = self.check_pack_scaled(lines)
        free = self.check_free_quantity(lines)
        drift = self.check_ledger_matches_balance(item_code)
        self.check_hand_corrections(item_code)
        if item_code:
            self.check_item_history(item_code)

        if options.get("export"):
            payload = {
                "lines_examined": len(lines),
                "pack_scaled": [
                    {"doc_no": ln.document.doc_no, "doc_type": ln.document.doc_type,
                     "line_id": ln.pk, "item": ln.item.code,
                     "unit_label": ln.unit_label, "qty_entered": ln.qty_entered,
                     "free_qty": ln.free_qty, "qty_base": ln.qty_base,
                     "line_net": str(ln.line_net), "cogs_total": str(ln.cogs_total)}
                    for ln in scaled
                ],
                "bonus_lines": [
                    {"doc_no": ln.document.doc_no, "item": ln.item.code,
                     "qty_entered": ln.qty_entered, "free_qty": ln.free_qty,
                     "qty_base": ln.qty_base}
                    for ln in free
                ],
                "balance_drift": drift,
            }
            with open(options["export"], "w") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
            self.stdout.write("")
            self._flag(f"Findings written to {options['export']} — "
                       "this file contains quantities and codes, no customer names.")

        self.stdout.write("")
        self.stdout.write(BAR)
        self.stdout.write("Done. No database row was created, changed or deleted.")
        self.stdout.write(BAR)
