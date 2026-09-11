"""R105: the spelling command that makes misspelled items findable again."""

import pytest
from django.core.management import call_command

from catalog.management.commands.fix_item_spellings import correct
from catalog.models import Item
from core.models import AuditLog, User


@pytest.fixture
def owner():
    return User.objects.create_user(username="own", password="x",
                                    role=User.Role.OWNER)


def make(code, name, generic_name=""):
    return Item.objects.create(code=code, name=name, generic_name=generic_name,
                               base_unit="pack", vat_exempt=True)


@pytest.mark.parametrize("before,after", [
    ("Embolectomy Cathater", "Embolectomy Catheter"),
    ("embolectomy cathater", "embolectomy catheter"),
    ("EMBOLECTOMY CATHATER", "EMBOLECTOMY CATHETER"),
    ("Folly cathater", "Folly catheter"),
    ("Tanxamic acid", "Tranexamic acid"),
    ("Amoxacillin 500mg APF", "Amoxicillin 500mg APF"),
    ("", ""),
])
def test_correct_replaces_the_word_and_keeps_its_shape(before, after):
    assert correct(before) == after


def test_correct_leaves_a_word_that_merely_contains_the_misspelling():
    """Whole words only — a longer word must not be rewritten mid-string."""
    assert correct("Cathaterisation") == "Cathaterisation"
    assert correct("catheter") == "catheter"


@pytest.mark.django_db
def test_the_command_makes_the_misspelled_item_findable(owner):
    item = make("ITM-0065", "Fogatery", generic_name="Embolectomy Cathater")
    assert not Item.objects.filter(generic_name__icontains="catheter").exists()

    call_command("fix_item_spellings", "--actor", owner.username)

    item.refresh_from_db()
    assert item.generic_name == "Embolectomy Catheter"
    assert Item.objects.filter(generic_name__icontains="catheter").count() == 1


@pytest.mark.django_db
def test_dry_run_reports_but_writes_nothing(owner):
    item = make("ITM-0065", "Fogatery", generic_name="Embolectomy Cathater")

    call_command("fix_item_spellings", "--dry-run", "--actor", owner.username)

    item.refresh_from_db()
    assert item.generic_name == "Embolectomy Cathater"
    assert not AuditLog.objects.filter(entity="Item").exists()


@pytest.mark.django_db
def test_every_change_is_audited(owner):
    item = make("ITM-0052", "Folly cathater", generic_name="Catheter 3 way 16G")

    call_command("fix_item_spellings", "--actor", owner.username)

    row = AuditLog.objects.get(entity="Item", entity_id=item.pk)
    assert row.before["name"] == "Folly cathater"
    assert row.after["name"] == "Folly catheter"
    # The generic was already correct, so it must survive untouched. `log_change`
    # records only the fields that changed (core/audit.py), so proving that means
    # reading the row back, not hunting for an unchanged key in the audit entry.
    item.refresh_from_db()
    assert item.generic_name == "Catheter 3 way 16G"
    assert "generic_name" not in row.after


@pytest.mark.django_db
def test_a_correctly_spelled_catalogue_is_left_alone(owner):
    make("ITM-0109", "catheter", generic_name="catheter")

    call_command("fix_item_spellings", "--actor", owner.username)

    assert not AuditLog.objects.filter(entity="Item").exists()
