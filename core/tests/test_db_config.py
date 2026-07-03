"""D66: the database must be PostgreSQL, bound to localhost (R45)."""

from django.conf import settings


def test_d66_postgresql_configuration():
    db = settings.DATABASES["default"]
    assert db["ENGINE"] == "django.db.backends.postgresql"
    assert db["HOST"] in ("localhost", "127.0.0.1")  # R45: never exposed on LAN
