"""D65: the database must be SQLite configured for safe concurrent posting."""

from django.conf import settings


def test_d65_sqlite_configuration():
    db = settings.DATABASES["default"]
    assert db["ENGINE"].endswith("sqlite3")
    options = db["OPTIONS"]
    assert options["transaction_mode"] == "IMMEDIATE"
    assert "journal_mode=WAL" in options["init_command"]
    assert options["timeout"] == 5
