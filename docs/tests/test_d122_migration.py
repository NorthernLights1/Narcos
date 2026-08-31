"""D122 migration, exercised for real rather than structurally.

Codex-MEDIUM: the first test for this asserted operation ordering and warning
text only. It could not have caught the defect that mattered — a converted
draft posting an opening lot at twelve times its true cost. This one migrates
a database back to 0009, builds rows through the historical models (which
still have `factor`), migrates forward, and checks what actually happened.
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)

# Rewinding `core` re-adds `unit_conversion_enabled` as NOT NULL, so the
# forward target MUST name core/0009 too. Migrating only `docs` back forward
# leaves that column in place and every later CompanySettings insert in the
# suite dies on a not-null violation.
BEFORE = [("docs", "0009_alter_document_due_date"),
          ("core", "0008_companysettings_books_closed_through")]
AFTER = [("docs", "0010_remove_documentline_factor"),
         ("core", "0009_remove_companysettings_unit_conversion_enabled")]


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    executor.loader.build_graph()
    return executor


@pytest.fixture
def at_0009():
    """Rewind to just before D122, yield the historical apps, then restore."""
    executor = _migrate(BEFORE)
    yield executor.loader.project_state(BEFORE).apps
    _migrate(AFTER)


def _seed(apps):
    User = apps.get_model("core", "User")
    Item = apps.get_model("catalog", "Item")
    Document = apps.get_model("docs", "Document")
    DocumentLine = apps.get_model("docs", "DocumentLine")

    owner = User.objects.create(username="boss", password="x", role="OWNER")
    item = Item.objects.create(code="PARA", name="Paracetamol",
                               base_unit="tablet", maintained_price="10.00")
    made = {}

    def line(status, factor, qty=10, free=0, notes="", doc_type="OPENING_STOCK"):
        doc = Document.objects.create(doc_type=doc_type, status=status,
                                      created_by=owner, notes=notes)
        return DocumentLine.objects.create(
            document=doc, item=item, qty_entered=qty, free_qty=free,
            factor=factor, unit_label="carton", unit_cost_entered="120.00")

    made["scaled_draft"] = line("DRAFT", 12)
    made["bonus_draft"] = line("DRAFT", 12, qty=10, free=2)
    made["plain_draft"] = line("DRAFT", 1)
    made["zero_draft"] = line("DRAFT", 0)
    made["long_note"] = line("DRAFT", 12, notes="x" * 5000)
    made["posted"] = line("POSTED", 12)
    return made


def test_the_migration_quarantines_only_pack_scaled_drafts(at_0009):
    apps = at_0009
    made = _seed(apps)
    _migrate(AFTER)

    from docs.models import Document, DocumentLine

    scaled = DocumentLine.objects.get(pk=made["scaled_draft"].pk)
    assert scaled.qty_entered == 0, "a pack-scaled draft is still postable"
    assert scaled.unit_label == "tablet", "the unit label still claims a pack"

    bonus = DocumentLine.objects.get(pk=made["bonus_draft"].pk)
    assert (bonus.qty_entered, bonus.free_qty) == (0, 0)

    plain = DocumentLine.objects.get(pk=made["plain_draft"].pk)
    assert plain.qty_entered == 10, "an ordinary factor-1 draft was disturbed"
    assert plain.unit_label == "carton"

    zero = DocumentLine.objects.get(pk=made["zero_draft"].pk)
    assert zero.qty_entered == 0, "a factor-0 draft was left alone"

    posted = DocumentLine.objects.get(pk=made["posted"].pk)
    assert posted.qty_entered == 10, "a POSTED line was modified — history rewritten"

    note = Document.objects.get(pk=made["scaled_draft"].document_id).notes
    assert "D122" in note and "PARA" in note and "x12" in note
    assert "re-enter" in note.lower()

    long_note = Document.objects.get(pk=made["long_note"].document_id).notes
    assert long_note.endswith("x" * 100), "an existing long note was truncated"


def test_the_migration_records_what_it_did(at_0009):
    apps = at_0009
    _seed(apps)
    _migrate(AFTER)

    from core.models import AuditLog

    rows = AuditLog.objects.filter(action="D122_DRAFT_QUARANTINED")
    assert rows.count() == 4, f"expected one audit row per quarantined draft, got {rows.count()}"
    assert any("PARA" in str(r.after) for r in rows)


def test_the_column_is_gone_afterwards(at_0009):
    _migrate(AFTER)
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'docs_documentline' AND column_name = 'factor'
        """)
        assert cursor.fetchone() is None
