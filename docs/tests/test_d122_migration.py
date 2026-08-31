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


def test_release_a_keeps_the_columns_and_new_rows_still_insert():
    """D122 ships as release A: the columns stay in the database and only
    leave Django's model state.

    The failure this guards is specific and total: `factor` and
    `unit_conversion_enabled` are NOT NULL with Django-level defaults only, so
    the moment Django stops naming them in INSERTs every write would violate
    the constraint. The migrations add database defaults; this proves it.
    """
    from decimal import Decimal as D

    from catalog.models import Item, Supplier
    from core.models import CompanySettings, User
    from docs.models import Document, DocType, DocumentLine

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT column_name, is_nullable, column_default
            FROM information_schema.columns
            WHERE (table_name, column_name) IN
                  (('docs_documentline', 'factor'),
                   ('core_companysettings', 'unit_conversion_enabled'))
            ORDER BY column_name
        """)
        columns = {name: (nullable, default) for name, nullable, default in cursor.fetchall()}

    assert "factor" in columns, "release A must KEEP docs_documentline.factor"
    assert "unit_conversion_enabled" in columns, \
        "release A must KEEP core_companysettings.unit_conversion_enabled"
    assert columns["factor"][1] is not None, \
        "factor is NOT NULL and Django no longer writes it — it needs a DB default"
    assert columns["unit_conversion_enabled"][1] is not None, \
        "unit_conversion_enabled is NOT NULL and Django no longer writes it"

    # The columns are gone from the model, so nothing can read or write them.
    assert not any(f.name == "factor" for f in DocumentLine._meta.get_fields())
    assert not hasattr(CompanySettings(), "unit_conversion_enabled")

    # And the real write paths still work.
    settings = CompanySettings.load()
    assert settings.pk == 1

    owner = User.objects.create_user("boss_a", password="pw", role=User.Role.OWNER)
    supplier = Supplier.objects.create(code="S-RA", name="Addis")
    item = Item.objects.create(code="RA-1", name="Paracetamol", base_unit="pack",
                               is_batch_tracked=False, has_expiry=False,
                               maintained_price=D("10.00"))
    doc = Document.objects.create(doc_type=DocType.RECEIVING, created_by=owner,
                                  supplier=supplier)
    line = DocumentLine.objects.create(document=doc, item=item, qty_entered=7,
                                       unit_cost_entered=D("5.00"), unit_label="pack")
    assert line.pk

    with connection.cursor() as cursor:
        cursor.execute("SELECT factor FROM docs_documentline WHERE id = %s", [line.pk])
        assert cursor.fetchone()[0] == 1, \
            "a row written without factor should take the database default of 1"


def test_the_itemunit_table_is_kept():
    """Release A: the alternate-unit table leaves model state, not the database."""
    from django.apps import apps

    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('catalog_itemunit')")
        assert cursor.fetchone()[0] is not None, \
            "release A must KEEP the catalog_itemunit table"

    with pytest.raises(LookupError):
        apps.get_model("catalog", "ItemUnit")
