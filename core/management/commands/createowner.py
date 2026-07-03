"""Create (or repair) the owner account from the local console (R10)."""

import getpass

from django.core.management.base import BaseCommand, CommandError

from core.models import User


class Command(BaseCommand):
    help = "Create an OWNER user, or reset an existing user's password to owner role."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--password", help="If omitted, prompts without echo.")

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"] or getpass.getpass("Password: ")
        if len(password) < 8:
            raise CommandError("Password must be at least 8 characters.")
        user, created = User.objects.get_or_create(username=username)
        user.role = User.Role.OWNER
        user.set_password(password)
        user.save()
        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} owner account '{username}'."))
