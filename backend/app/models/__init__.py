"""Import all models here so Alembic autogenerate sees them."""

from app.models.audit import AuditLog
from app.models.event import (
    Assessment,
    Event,
    EventEvidence,
    EventStatus,
    EvidenceRelation,
    Priority,
)
from app.models.field_report import FieldReport, FieldReportMedia, ReportStatus
from app.models.user import Role, User

__all__ = [
    "Assessment",
    "AuditLog",
    "Event",
    "EventEvidence",
    "EventStatus",
    "EvidenceRelation",
    "FieldReport",
    "FieldReportMedia",
    "Priority",
    "ReportStatus",
    "Role",
    "User",
]
