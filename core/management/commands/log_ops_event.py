from django.core.management.base import BaseCommand

from core.audit import log_event


class Command(BaseCommand):
    help = "Write an ops audit event."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["BACKUP", "RESTORE", "UPDATE"])
        parser.add_argument("--detail", default="")

    def handle(self, *args, **options):
        row = log_event(
            None,
            options["action"],
            "Ops",
            detail={"detail": options["detail"]},
        )
        self.stdout.write(self.style.SUCCESS(f"Logged {row.action} audit event."))
