"""Audit helper (D47): diff-based change logging. Values stored as strings."""

from decimal import Decimal

from core.models import AuditLog


def _as_str(value) -> str:
    # Decimals differ cosmetically between DB reads ("15.00") and form input
    # ("15"); normalize so the diff only sees real changes.
    if isinstance(value, Decimal):
        text = f"{value:f}"
        return text.rstrip("0").rstrip(".") if "." in text else text
    return str(value)


def snapshot(instance, fields: list[str]) -> dict[str, str]:
    return {f: _as_str(getattr(instance, f)) for f in fields}


def log_change(actor, action: str, entity: str, entity_id, before: dict, after: dict):
    """Write one audit row holding only the fields that changed.
    Returns the row, or None when nothing changed (no noise in the log)."""
    changed = {k for k in after if before.get(k) != after[k]}
    changed |= {k for k in before if k not in after}
    if not changed:
        return None
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        before={k: before[k] for k in sorted(changed) if k in before},
        after={k: after[k] for k in sorted(changed) if k in after},
    )


def log_event(actor, action: str, entity: str, entity_id="", detail: dict | None = None):
    """Write one audit row for a non-diff event (login of note, posting, etc.)."""
    return AuditLog.objects.create(
        actor=actor, action=action, entity=entity, entity_id=str(entity_id),
        before=None, after=detail,
    )
