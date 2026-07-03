from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command

from core.models import AuditLog, User

pytestmark = pytest.mark.django_db


def test_reset_owner_password_resets_single_owner():
    user = User.objects.create_user("owner", password="old-pass-123", role=User.Role.OWNER)
    out = StringIO()
    call_command("reset_owner_password", "--password", "new-pass-123", stdout=out)
    user.refresh_from_db()
    assert user.check_password("new-pass-123")
    assert "Reset owner password" in out.getvalue()


def test_reset_owner_password_promotes_named_user():
    user = User.objects.create_user("staff", password="old-pass-123", role=User.Role.EMPLOYEE)
    call_command("reset_owner_password", "staff", "--password", "new-pass-123")
    user.refresh_from_db()
    assert user.is_owner
    assert user.check_password("new-pass-123")


def test_log_ops_event_command_writes_audit_row():
    call_command("log_ops_event", "BACKUP", "--detail", "D:/NarcosBackups/latest")
    row = AuditLog.objects.get(action="BACKUP", entity="Ops")
    assert row.actor is None
    assert row.after == {"detail": "D:/NarcosBackups/latest"}


def test_ops_runbook_and_scripts_cover_p10():
    root = Path(__file__).resolve().parents[2]
    runbook = (root / "ops" / "RUNBOOK.md").read_text(encoding="utf-8")
    backup_script = (root / "scripts" / "backup.ps1").read_text(encoding="utf-8")
    restore_script = (root / "scripts" / "restore.ps1").read_text(encoding="utf-8")
    assert "reset_owner_password" in runbook
    assert "Task Scheduler" in runbook
    assert "pg_restore" in runbook
    assert "Waitress" in runbook
    assert "localhost" in runbook
    assert "Ethiopic names render in print" in runbook
    assert "log_ops_event BACKUP" in backup_script
    assert "log_ops_event RESTORE" in restore_script
    assert (root / "scripts" / "backup.ps1").exists()
    assert (root / "scripts" / "restore.ps1").exists()
