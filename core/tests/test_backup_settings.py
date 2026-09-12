"""D147: backup paths and interval in Settings, and how they reach the backup.

The app is in a container; `ops/docker-backup.ps1` runs on Windows under Task
Scheduler. A setting typed here reaches the backup only because both containers
mount the host's backup folder, so saving Settings writes one file there and the
script reads it on its next run.

The rule these tests exist to hold: **a setting no code enforces must not ship,
and a backup setting you cannot check is how this client went a month with no
backup.** So the hand-over is written, read back, and shown on the page.
"""

import json
from pathlib import Path

import pytest
from django.urls import reverse

from core.backup_schedule import (
    read_schedule,
    schedule_payload,
    write_schedule,
)
from core.forms import CompanySettingsForm
from core.models import AuditLog, CompanySettings, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


@pytest.fixture
def staff():
    return User.objects.create_user("clerk", password="pw", role=User.Role.EMPLOYEE)


@pytest.fixture
def backup_dir(tmp_path, settings):
    """Stand in for `/backups`, which only exists inside the container."""
    settings.NARCOS_BACKUP_DIR = str(tmp_path)
    return tmp_path


def _settings(**overrides):
    company = CompanySettings.load()
    for field, value in overrides.items():
        setattr(company, field, value)
    company.save()
    return company


def _post_data(**overrides):
    company = CompanySettings.load()
    data = {field: getattr(company, field)
            for field in CompanySettings.AUDITED_FIELDS}
    data = {key: ("" if value is None else value) for key, value in data.items()}
    data.update(overrides)
    return data


# --- the defaults ---------------------------------------------------------

def test_out_of_the_box_nothing_changes(backup_dir):
    """Blank paths and a daily interval describe exactly what the script did
    before this existed."""
    company = CompanySettings.load()
    assert company.backup_primary_path == ""
    assert company.backup_secondary_path == ""
    assert company.backup_interval_days == 1
    assert company.backup_keep_count == 14


def test_the_four_settings_are_audited():
    """D47: a change to where the backups go must be attributable."""
    for field in ("backup_primary_path", "backup_secondary_path",
                  "backup_interval_days", "backup_keep_count"):
        assert field in CompanySettings.AUDITED_FIELDS


# --- the bridge file ------------------------------------------------------

def test_the_payload_carries_only_what_the_script_acts_on(backup_dir, owner):
    company = _settings(backup_primary_path="D:\\NarcosBackups",
                        backup_secondary_path="E:\\offsite",
                        backup_interval_days=2, backup_keep_count=30)
    payload = schedule_payload(company, owner)
    assert payload["primary_path"] == "D:\\NarcosBackups"
    assert payload["secondary_path"] == "E:\\offsite"
    assert payload["interval_days"] == 2
    assert payload["keep_count"] == 30
    assert payload["written_by"] == "boss"
    assert payload["written_at"]


def test_writing_the_file_puts_readable_json_where_the_script_looks(
        backup_dir, owner):
    company = _settings(backup_primary_path="D:\\NarcosBackups")
    path, problem = write_schedule(company, owner)
    assert problem is None
    assert path == backup_dir / "schedule.json"
    assert json.loads(path.read_text())["primary_path"] == "D:\\NarcosBackups"
    assert read_schedule()["primary_path"] == "D:\\NarcosBackups"


def test_a_folder_it_cannot_write_reports_rather_than_raises(settings, owner):
    """Failing to hand the settings over must not also fail the save."""
    settings.NARCOS_BACKUP_DIR = "/proc/one/cannot/write/here"
    _path, problem = write_schedule(CompanySettings.load(), owner)
    assert problem


def test_reading_a_missing_file_is_not_an_error(settings, tmp_path):
    settings.NARCOS_BACKUP_DIR = str(tmp_path / "nothing-here")
    assert read_schedule() is None


def test_reading_a_corrupt_file_is_not_an_error(backup_dir):
    (backup_dir / "schedule.json").write_text("{not json")
    assert read_schedule() is None


# --- saving from the page -------------------------------------------------

def test_saving_settings_hands_them_to_the_backup(client, owner, backup_dir):
    client.force_login(owner)
    response = client.post(reverse("company_settings"),
                           _post_data(backup_primary_path="D:\\NarcosBackups",
                                      backup_secondary_path="E:\\offsite",
                                      backup_interval_days=3))
    assert response.status_code == 302
    handed = json.loads((backup_dir / "schedule.json").read_text())
    assert handed["primary_path"] == "D:\\NarcosBackups"
    assert handed["secondary_path"] == "E:\\offsite"
    assert handed["interval_days"] == 3


def test_the_settings_still_save_when_the_hand_over_fails(client, owner,
                                                          settings):
    settings.NARCOS_BACKUP_DIR = "/proc/one/cannot/write/here"
    client.force_login(owner)
    response = client.post(reverse("company_settings"),
                           _post_data(backup_interval_days=5), follow=True)
    assert CompanySettings.load().backup_interval_days == 5
    assert b"could not be written" in response.content


def test_the_page_shows_what_the_backup_will_use(client, owner, backup_dir):
    client.force_login(owner)
    client.post(reverse("company_settings"),
                _post_data(backup_primary_path="D:\\NarcosBackups"))
    content = client.get(reverse("company_settings")).content.decode()
    assert "What the backup is using" in content
    assert "D:\\NarcosBackups" in content


def test_the_page_says_so_when_no_backup_was_ever_recorded(client, owner,
                                                           backup_dir):
    client.force_login(owner)
    content = client.get(reverse("company_settings")).content.decode()
    assert "No backup has ever been recorded" in content


def test_the_page_shows_the_last_recorded_backup(client, owner, backup_dir):
    AuditLog.objects.create(actor=None, action="BACKUP", entity="Ops",
                            after={"detail": "20260912-160000"})
    client.force_login(owner)
    content = client.get(reverse("company_settings")).content.decode()
    assert "20260912-160000" in content


def test_an_employee_cannot_reach_the_settings(client, staff):
    client.force_login(staff)
    assert client.get(reverse("company_settings")).status_code == 403


# --- what the form refuses ------------------------------------------------

def _form(**overrides):
    return CompanySettingsForm(_post_data(**overrides),
                               instance=CompanySettings.load())


def test_a_path_without_a_drive_is_refused():
    """The script would read it against whatever folder it runs in."""
    form = _form(backup_primary_path="backups")
    assert not form.is_valid()
    assert "backup_primary_path" in form.errors


def test_a_drive_path_is_accepted():
    assert _form(backup_primary_path="D:\\NarcosBackups").is_valid()


def test_a_network_share_is_accepted():
    assert _form(backup_primary_path="\\\\fileserver\\narcos").is_valid()


def test_a_forward_slash_drive_path_is_accepted():
    assert _form(backup_primary_path="D:/NarcosBackups").is_valid()


def test_both_copies_in_one_folder_is_refused():
    """Two copies in one folder is one copy with extra steps."""
    form = _form(backup_primary_path="D:\\NarcosBackups",
                 backup_secondary_path="D:\\NarcosBackups\\")
    assert not form.is_valid()
    assert "backup_secondary_path" in form.errors


def test_blank_paths_are_fine():
    assert _form(backup_primary_path="", backup_secondary_path="").is_valid()


@pytest.mark.parametrize("days", [0, 31])
def test_an_impossible_interval_is_refused(days):
    assert not _form(backup_interval_days=days).is_valid()


@pytest.mark.parametrize("count", [6, 366])
def test_an_impossible_retention_is_refused(count):
    assert not _form(backup_keep_count=count).is_valid()


def test_keeping_fewer_than_a_week_is_refused():
    """R97 territory: retention is what nearly deleted the last good backup."""
    assert not _form(backup_keep_count=1).is_valid()


# --- what the Windows script does with them -------------------------------

def _script():
    root = Path(__file__).resolve().parents[2]
    return (root / "ops" / "docker-backup.ps1").read_text(encoding="utf-8")


def test_the_script_reads_the_handed_over_settings():
    script = _script()
    assert "schedule.json" in script
    assert "interval_days" in script
    assert "keep_count" in script
    assert "primary_path" in script
    assert "secondary_path" in script


def test_the_script_skips_rather_than_runs_when_inside_the_interval():
    assert "BACKUP SKIPPED" in _script()


def test_the_script_verifies_every_copy_by_size():
    script = _script()
    assert "Copy-BackupTo" in script
    assert ".Length -ne $f.Length" in script


def test_a_missing_second_drive_warns_and_the_backup_still_counts():
    """An unplugged USB stick must never cost the backup that did work."""
    script = _script()
    assert "[void](Copy-BackupTo $SecondaryPath)" in script
    assert "[void](Copy-BackupTo $PrimaryPath -Fatal)" in script


def test_the_script_never_prunes_a_destination_with_no_good_backup():
    assert "if ($complete.Count -eq 0) { return }" in _script()


def test_the_newest_good_backup_is_never_prunable():
    assert "[void]$keep.Add($complete[0].Name)" in _script()
