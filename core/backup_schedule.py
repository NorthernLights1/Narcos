"""D147: carrying the backup settings out to the script that does the backup.

The app runs in a container. **The backup does not.** `ops/docker-backup.ps1`
runs on Windows under Task Scheduler and reaches into the containers with
`docker compose exec`. Django cannot see `E:\\`, cannot create a scheduled task
and cannot restart the stack.

There is already a road between them: both containers mount the host's
`NARCOS_BACKUP_ROOT` at `/backups` (`compose.yml`). Saving Settings writes one
small file there; the script reads it on the host on its next run. No new mount,
no new service, nothing over the network.

**A missing or unreadable file must never stop a backup.** The script falls back
to exactly what it does today, which is why every failure here is reported to the
person saving settings rather than raised.
"""

import json
from pathlib import Path

from django.conf import settings as django_settings
from django.utils import timezone

SCHEDULE_FILENAME = "schedule.json"


def schedule_path() -> Path:
    """Where the bridge file goes. `/backups` in the container, overridable so a
    development machine can point it somewhere real."""
    return Path(getattr(django_settings, "NARCOS_BACKUP_DIR", "/backups")) \
        / SCHEDULE_FILENAME


def schedule_payload(company_settings, actor=None) -> dict:
    """Only what the script acts on, plus who to ask about it.

    Paths travel as typed. The app cannot check that a Windows path exists — it
    is a different machine's filesystem — so the proof that a path was right is
    the run's own report, not a tick here.
    """
    return {
        "written_at": timezone.now().isoformat(timespec="seconds"),
        "written_by": getattr(actor, "username", "") or "",
        "primary_path": company_settings.backup_primary_path.strip(),
        "secondary_path": company_settings.backup_secondary_path.strip(),
        "interval_days": company_settings.backup_interval_days,
        "keep_count": company_settings.backup_keep_count,
    }


def write_schedule(company_settings, actor=None):
    """Write the bridge file. Returns (path, error) — `error` is a sentence for
    the person, never an exception, because failing to hand the settings over
    must not also fail the save."""
    target = schedule_path()
    payload = schedule_payload(company_settings, actor)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as problem:
        return target, str(problem)
    return target, None


def read_schedule():
    """What the script will read on its next run, or None. Shown back on the
    settings page so the hand-over is visible rather than assumed."""
    try:
        return json.loads(schedule_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
