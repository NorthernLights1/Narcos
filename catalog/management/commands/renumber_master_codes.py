"""One-time migration of hand-typed master codes to the automatic scheme
(ITM-/CUS-/SUP-). Every change is written to the audit log (D47)."""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import Customer, Item, Supplier, MASTER_CODE_PREFIXES
from core.audit import log_change
from core.models import NumberSequence, User


class Command(BaseCommand):
    help = ("Replace hand-typed item/customer/supplier codes with auto-assigned "
            "ones. Codes already in the auto scheme are left alone.")

    def add_arguments(self, parser):
        parser.add_argument("--actor", help="Username recorded in the audit log "
                            "(default: the sole owner account).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Show what would change without saving.")

    def handle(self, *args, **options):
        if options["actor"]:
            actor = User.objects.get(username=options["actor"])
        else:
            owners = User.objects.filter(role=User.Role.OWNER)
            if owners.count() != 1:
                raise CommandError("Multiple owners — pass --actor USERNAME.")
            actor = owners.get()

        with transaction.atomic():
            for model in (Item, Customer, Supplier):
                prefix = MASTER_CODE_PREFIXES[model.__name__]
                rows = [obj for obj in model.objects.order_by("pk")
                        if not obj.code.startswith(f"{prefix}-")]
                if rows and not options["dry_run"]:
                    # Start the sequence fresh; the assign loop walks past any
                    # number a kept legacy code might occupy.
                    NumberSequence.objects.filter(
                        doc_type=f"CODE_{model.__name__.upper()}"
                    ).delete()
                for obj in rows:
                    old = obj.code
                    if options["dry_run"]:
                        self.stdout.write(f"{model.__name__}: {old} -> (auto)")
                        continue
                    obj.code = ""
                    obj.save()
                    log_change(actor=actor, action="MASTER_UPDATE",
                               entity=model.__name__, entity_id=obj.pk,
                               before={"code": old}, after={"code": obj.code})
                    self.stdout.write(f"{model.__name__}: {old} -> {obj.code}")
            if options["dry_run"]:
                transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS("Done."))
