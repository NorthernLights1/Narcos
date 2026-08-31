# D122: the alternate-unit table leaves Django's model state but STAYS in the
# database.
#
# Dropping it is not reversible on the client's box — NARCOS_IMAGE is an
# unpinned `:latest` (compose.yml:27) and ops/docker-restore.ps1 refuses a
# database that already has tables, so there is no way back to the old image
# once the rows are gone. Any pack sizes the business had declared are data,
# and R65 only sampled the working database three weeks before this was
# written; it is not proof the table is empty today.
#
# The foreign key to catalog_item IS dropped, though the table and its rows
# stay. Leaving it was the first attempt and it is not harmless: an orphaned
# table that Django no longer knows about, still referencing a table it does,
# blocks TRUNCATE on the parent — which is how Django flushes between tests,
# and it failed immediately. Keeping a dangling constraint also means a table
# nothing manages can veto operations on one that is managed. Dropping the FK
# leaves a genuinely inert archive: the data is preserved, the coupling is not.
#
# TODO(release B): drop the constraints and the table once D122 has run clean
# at the client for a full cycle. Tracked in 03-open-risks.md.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0002_customer_city_customer_license_no_customer_mobile'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveConstraint(
                    model_name='itemunit',
                    name='uniq_item_unit_label',
                ),
                migrations.RemoveConstraint(
                    model_name='itemunit',
                    name='unit_factor_gt_1',
                ),
                migrations.DeleteModel(
                    name='ItemUnit',
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    # By name lookup, not a hardcoded identifier: Django's FK
                    # constraint names carry a hash and differ between installs.
                    """
                    DO $$
                    DECLARE constraint_name text;
                    BEGIN
                        IF to_regclass('catalog_itemunit') IS NULL THEN
                            RETURN;
                        END IF;
                        FOR constraint_name IN
                            SELECT conname FROM pg_constraint
                            WHERE conrelid = 'catalog_itemunit'::regclass
                              AND contype = 'f'
                        LOOP
                            EXECUTE format(
                                'ALTER TABLE catalog_itemunit DROP CONSTRAINT %I',
                                constraint_name);
                        END LOOP;
                    END $$;
                    """,
                    # Not restorable: the rows may by then reference items that
                    # no longer exist, so re-adding the constraint could fail.
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
