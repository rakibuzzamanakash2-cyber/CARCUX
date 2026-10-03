"""Writing audit records. Callers commit; the record is part of the same transaction."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


class AuditAction:
    LOGIN_SUCCEEDED = "auth.login_succeeded"
    LOGIN_FAILED = "auth.login_failed"
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_BOOTSTRAPPED = "user.bootstrapped"
    FIELD_REPORT_SUBMITTED = "field_report.submitted"
    FIELD_REPORT_VERIFIED = "field_report.verified"
    EVENT_CREATED = "event.created"
    EVENT_UPDATED = "event.updated"
    EVIDENCE_LINKED = "event.evidence_linked"
    EVIDENCE_UPDATED = "event.evidence_updated"
    EVIDENCE_UNLINKED = "event.evidence_unlinked"
    FIELD_REPORT_REVIEWED = "field_report.reviewed"
    PASSWORD_CHANGED = "auth.password_changed"  # noqa: S105 (an action name)
    PASSWORD_CHANGE_FAILED = "auth.password_change_failed"  # noqa: S105
    PASSWORD_RESET = "user.password_reset"  # noqa: S105
    SIGNAL_ENTERED = "signal.entered"
    SIGNAL_REVIEWED = "signal.reviewed"
    SOURCE_CREATED = "source.created"
    SOURCE_UPDATED = "source.updated"
    SOURCE_FETCHED = "source.fetched"
    DATASET_EXPORTED = "dataset.exported"


def record(
    db: Session,
    action: str,
    *,
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | uuid.UUID | None = None,
    ip_address: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        actor_id=actor_id,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        ip_address=ip_address,
        details=details or {},
    )
    db.add(entry)
    return entry
