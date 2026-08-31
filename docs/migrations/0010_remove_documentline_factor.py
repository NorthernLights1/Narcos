"""D122: drop the pack multiplier.

A DRAFT line is the one place the multiplier cannot simply be forgotten: it
carries `factor` but `qty_base` is still 0, so after the column goes a draft
that meant "5 cartons of 12" would post as five base units.

The first attempt at this converted the quantity and left the money alone, on
the theory that a total reading twelve times too high gets noticed before
posting. Codex disproved the premise: `doc.notes` is never rendered on the
draft detail page, opening-stock drafts get no total preview at all, and that
page offers a direct Post button. A converted draft would have posted an
opening lot at 120.00 per base unit instead of 10.00 — frozen forever, because
`CostLot` is immutable.

So these drafts are QUARANTINED, not converted. Setting `qty_entered` and
`free_qty` to 0 makes them impossible to post — every handler refuses a
non-positive quantity — so the failure lands loudly at the moment someone
tries, instead of silently in a frozen cost lot. The unit label is reset to
the item's base unit so it stops claiming a pack, the original figures are
recorded in `notes` and in an audit row, and the owner re-enters the line
deliberately.

Deliberately does not raise: `docker-entrypoint.sh` runs `migrate` under
`set -e`, so a raising migration exits the container and Docker restarts it
forever with nothing on screen.
"""

from django.db import migrations

WARNING = (
    "*** D122: this draft was typed in packs, and the pack multiplier no "
    "longer exists. Its quantities have been cleared so it cannot post with "
    "the wrong ones ({detail}). Re-enter each line in {unit}, then delete "
    "this note. ***"
)


def quarantine_pack_scaled_drafts(apps, schema_editor):
    DocumentLine = apps.get_model("docs", "DocumentLine")
    Document = apps.get_model("docs", "Document")
    AuditLog = apps.get_model("core", "AuditLog")

    affected = (DocumentLine.objects
                .filter(document__status="DRAFT")
                .exclude(factor=1)
                .select_related("document", "item"))

    by_document = {}
    for line in affected:
        by_document.setdefault(line.document_id, []).append(line)

    for document_id, lines in by_document.items():
        detail, units = [], set()
        for line in lines:
            detail.append(
                f"{line.item.code}: was {line.qty_entered}"
                + (f"+{line.free_qty} free" if line.free_qty else "")
                + f" x{line.factor} {line.unit_label or ''}".rstrip()
                + f" @ {line.unit_cost_entered or line.unit_price}"
            )
            units.add(line.item.base_unit)
            line.qty_entered = 0
            line.free_qty = 0
            line.unit_label = line.item.base_unit
            line.save(update_fields=["qty_entered", "free_qty", "unit_label"])

        document = Document.objects.get(pk=document_id)
        document.notes = (
            WARNING.format(detail="; ".join(detail),
                           unit=", ".join(sorted(units)) or "base units")
            + "\n" + (document.notes or "")
        )
        document.save(update_fields=["notes"])
        AuditLog.objects.create(
            actor=None, action="D122_DRAFT_QUARANTINED", entity="Document",
            entity_id=str(document_id), before=None, after={"lines": detail},
        )


def unquarantine(apps, schema_editor):
    """Reversing restores the column with default 1. The original per-line
    factors and quantities are not restored — the audit rows written above,
    and the note on each draft, are the record of what they were."""


class Migration(migrations.Migration):

    dependencies = [
        ('docs', '0009_alter_document_due_date'),
        ('core', '0008_companysettings_books_closed_through'),
    ]

    operations = [
        migrations.RunPython(quarantine_pack_scaled_drafts, unquarantine),
        # D122 ships as "release A": the column STAYS in the database and only
        # leaves Django's model state, so no code reads or writes it. Dropping
        # it is not reversible on the client's box — NARCOS_IMAGE is an
        # unpinned `:latest` (compose.yml:27) and ops/docker-restore.ps1
        # refuses a database that already has tables, so there is no way back
        # to the old image once the data is gone. The historical per-line
        # factors are also the only record of what pre-D122 documents meant.
        #
        # `factor` is NOT NULL with only a Django-level default, so the moment
        # Django stops naming it in INSERTs every new line would violate the
        # constraint. A database default of 1 fixes that and is exactly right
        # semantically: after D122 every new line is on a single scale.
        #
        # TODO(release B): drop the column once this has run clean at the
        # client for a full cycle. Tracked in 03-open-risks.md.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name='documentline', name='factor'),
            ],
            database_operations=[
                migrations.RunSQL(
                    "ALTER TABLE docs_documentline ALTER COLUMN factor SET DEFAULT 1",
                    reverse_sql="ALTER TABLE docs_documentline ALTER COLUMN factor DROP DEFAULT",
                ),
            ],
        ),
    ]
