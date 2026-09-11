"""R105: correct misspelled words in item names and generic names.

The client reported that "catheter is not in my database". Part of it was the
Inventory search (fixed in code); the rest is this — three items spell the
generic `Embolectomy Cathater`, so the correct spelling finds nothing on any
screen. Data is never hand-edited on the client's machine (see CLAUDE.md), so
the correction ships as this command and the owner runs it.

Whole words only, case preserved, every change written to the audit log (D47).
Run with --dry-run first and read the list before committing to it.
"""

import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import Item
from core.audit import log_change
from core.models import User

# Misspelling -> correction. Keys are matched as whole words, case-insensitively.
# Add to this table rather than writing a second command.
SPELLINGS = {
    "cathater": "catheter",
    "endothracheal": "endotracheal",
    "tanxamic": "tranexamic",
    "tranxamic": "tranexamic",
    "amoxacillin": "amoxicillin",
    "omeprazol": "omeprazole",
    "colestomy": "colostomy",
}

FIELDS = ("name", "generic_name")


def _match_case(source: str, replacement: str) -> str:
    """Keep the shape the operator typed: ALL CAPS, Title, or lower."""
    if source.isupper():
        return replacement.upper()
    if source[:1].isupper():
        return replacement.capitalize()
    return replacement


def correct(text: str) -> str:
    """Replace every misspelled whole word in `text`. Pure, so it is testable."""
    if not text:
        return text
    for wrong, right in SPELLINGS.items():
        text = re.sub(
            rf"\b{re.escape(wrong)}\b",
            lambda m: _match_case(m.group(0), right),
            text,
            flags=re.IGNORECASE,
        )
    return text


class Command(BaseCommand):
    help = ("Correct known misspellings in item names and generic names so the "
            "item can be found by its correct spelling. Audited (D47).")

    def add_arguments(self, parser):
        parser.add_argument("--actor", help="Username recorded in the audit log "
                            "(default: the sole owner account).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Show what would change without saving.")

    def _actor(self, username):
        if username:
            return User.objects.get(username=username)
        owners = User.objects.filter(role=User.Role.OWNER)
        if owners.count() != 1:
            raise CommandError("Multiple owners — pass --actor USERNAME.")
        return owners.get()

    def handle(self, *args, **options):
        actor = self._actor(options["actor"])
        changed = 0
        with transaction.atomic():
            for item in Item.objects.order_by("code"):
                before = {f: getattr(item, f) for f in FIELDS}
                after = {f: correct(before[f]) for f in FIELDS}
                if after == before:
                    continue
                changed += 1
                for field in FIELDS:
                    if before[field] != after[field]:
                        self.stdout.write(
                            f"{item.code} {field}: {before[field]!r} -> {after[field]!r}"
                        )
                if options["dry_run"]:
                    continue
                for field in FIELDS:
                    setattr(item, field, after[field])
                item.save(update_fields=list(FIELDS))
                log_change(actor=actor, action="MASTER_UPDATE", entity="Item",
                           entity_id=item.pk, before=before, after=after)
            if options["dry_run"]:
                transaction.set_rollback(True)

        if not changed:
            self.stdout.write(self.style.SUCCESS("Nothing to correct."))
            return
        verb = "would change" if options["dry_run"] else "changed"
        self.stdout.write(self.style.SUCCESS(f"{changed} item(s) {verb}."))
