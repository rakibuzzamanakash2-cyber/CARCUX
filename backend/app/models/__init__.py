"""Import all models here so Alembic autogenerate sees them."""

from app.models.assessment import AssessmentModel
from app.models.audit import AuditLog
from app.models.copy import CopyDecision
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
from app.models.official import OfficialPage, PageKind, PageStatus, VerificationMethod
from app.models.public import (
    AccountStatus,
    CommentReport,
    IncidentOpinion,
    OpinionReport,
    PublicAccount,
    StatementComment,
    StatementLike,
)
from app.models.signal import (
    Adapter,
    IngestRun,
    Severity,
    Signal,
    SignalStatus,
    Source,
    SourceType,
)
from app.models.statement import Finding, Statement
from app.models.suggestion import SuggestionModel
from app.models.user import Role, User

__all__ = [
    "AccountStatus",
    "CommentReport",
    "IncidentOpinion",
    "OpinionReport",
    "PublicAccount",
    "StatementComment",
    "StatementLike",
    "Adapter",
    "Assessment",
    "AssessmentModel",
    "AuditLog",
    "CopyDecision",
    "Event",
    "EventEvidence",
    "EventStatus",
    "EvidenceJudgement",
    "EvidenceRelation",
    "FieldReport",
    "FieldReportMedia",
    "Finding",
    "IngestRun",
    "OfficialPage",
    "PageKind",
    "PageStatus",
    "Priority",
    "ReportStatus",
    "Severity",
    "Signal",
    "SignalStatus",
    "Source",
    "SourceType",
    "Statement",
    "SuggestionModel",
    "Role",
    "User",
    "VerificationMethod",
]
