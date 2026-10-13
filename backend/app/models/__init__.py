"""Import all models here so Alembic autogenerate sees them."""

from app.models.audit import AuditLog
from app.models.event import (
    Assessment,
    Event,
    EventEvidence,
    EventStatus,
    EvidenceJudgement,
    EvidenceRelation,
    Priority,
)
from app.models.field_report import FieldReport, FieldReportMedia, ReportStatus
from app.models.signal import (
    Adapter,
    IngestRun,
    Severity,
    Signal,
    SignalStatus,
    Source,
    SourceType,
)
from app.models.suggestion import SuggestionModel
from app.models.user import Role, User

__all__ = [
    "Adapter",
    "Assessment",
    "AuditLog",
    "Event",
    "EventEvidence",
    "EventStatus",
    "EvidenceJudgement",
    "EvidenceRelation",
    "FieldReport",
    "FieldReportMedia",
    "IngestRun",
    "Priority",
    "ReportStatus",
    "Severity",
    "Signal",
    "SignalStatus",
    "Source",
    "SourceType",
    "SuggestionModel",
    "Role",
    "User",
]
