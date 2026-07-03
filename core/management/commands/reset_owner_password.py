import getpass

from django.core.management.base import BaseCommand, CommandError

from core.models import User


class Command(BaseCommand):
    help = "Reset an owner password from the local console."

    def add_arguments(self, parser):
        parser.add_argument("username", nargs="?")
        parser.add_argument("--password", help="If omitted, prompts without echo.")

    def handle(self, *args, **options):
        username = options["username"]
        if username:
            user = User.objects.filter(username=username).first()
            if user is None:
                raise CommandError(f"User '{username}' does not exist.")
        else:
            owners = User.objects.filter(role=User.Role.OWNER)
            if owners.count() != 1:
                raise CommandError("Pass a username when there is not exactly one owner.")
            user = owners.get()

        password = options["password"] or getpass.getpass("New password: ")
        if len(password) < 8:
            raise CommandError("Password must be at least 8 characters.")
        user.role = User.Role.OWNER
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Reset owner password for '{user.username}'."))
