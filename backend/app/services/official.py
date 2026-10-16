"""Official pages: creation, verification, suspension and their official accounts.

Verification is a human act by an admin. CARCUX records what was checked: either the
office confirmed through its own email address (the address and a note), or an official
letter was received (its scan, stored with a SHA-256 so it cannot be swapped silently).
"""

import hashlib
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.official import OfficialPage, PageStatus, VerificationMethod
from app.models.user import Role, User
from app.services import audit
from app.services.media import resolve
from app.services.users import normalise_email

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
# Decided by the bytes, never by the file name or the browser's content type.
_DOCUMENT_TYPES = (
    (b"%PDF-", "application/pdf", "pdf"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
)
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class OfficialPageError(ValueError):
    """A rule about official pages was not met; the message says which."""


def check_slug(value: str) -> str:
    slug = value.strip().lower()
    if not 3 <= len(slug) <= 60 or not _SLUG.fullmatch(slug):
        raise OfficialPageError(
            "The page address must be 3 to 60 lowercase letters, digits and dashes"
        )
    return slug


def by_slug(db: Session, slug: str) -> OfficialPage | None:
    return db.scalar(select(OfficialPage).where(OfficialPage.slug == slug.lower()))


def visible_to(page: OfficialPage, user: User) -> bool:
    """Verified pages are visible to everyone signed in; others to admins and members."""
    return (
        page.status == PageStatus.VERIFIED
        or user.role == Role.ADMIN
        or user.official_page_id == page.id
    )


def create(db: Session, *, actor: User, ip: str | None, **fields) -> OfficialPage:
    fields["slug"] = check_slug(fields["slug"])
    if by_slug(db, fields["slug"]):
        raise OfficialPageError("That page address is already taken")
    if fields.get("contact_email"):
        fields["contact_email"] = normalise_email(fields["contact_email"])
    page = OfficialPage(id=uuid.uuid4(), created_by_id=actor.id, **fields)
    db.add(page)
    db.flush()
    audit.record(
        db, audit.AuditAction.OFFICIAL_PAGE_CREATED, actor_id=actor.id,
        target_type="official_page", target_id=page.id, ip_address=ip,
        details={"slug": page.slug, "name": page.name, "kind": page.kind.value},
    )  # fmt: skip
    return page


def update(db: Session, page: OfficialPage, changes: dict, *, actor: User, ip: str | None):
    if "contact_email" in changes and changes["contact_email"]:
        changes["contact_email"] = normalise_email(changes["contact_email"])
    before = {k: getattr(page, k) for k in changes}
    for key, value in changes.items():
        setattr(page, key, value)
    audit.record(
        db, audit.AuditAction.OFFICIAL_PAGE_UPDATED, actor_id=actor.id,
        target_type="official_page", target_id=page.id, ip_address=ip,
        details={"changes": {k: {"from": _plain(before[k]), "to": _plain(v)}
                             for k, v in changes.items()}},
    )  # fmt: skip


def _plain(value):
    return value.value if hasattr(value, "value") else value


def check_document(data: bytes) -> tuple[str, str]:
    if not data:
        raise OfficialPageError("The file is empty")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise OfficialPageError("The file is larger than 10 MB")
    for magic, content_type, extension in _DOCUMENT_TYPES:
        if data.startswith(magic):
            return content_type, extension
    raise OfficialPageError("The letter must be a PDF, JPEG or PNG file")


def add_document(
    db: Session, page: OfficialPage, data: bytes, media_dir: Path, *, actor: User, ip: str | None
) -> None:
    content_type, extension = check_document(data)
    key = f"official_pages/{page.id}/{uuid.uuid4()}.{extension}"
    path = resolve(media_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    page.document_key, page.document_type = key, content_type
    page.document_sha256 = hashlib.sha256(data).hexdigest()
    audit.record(
        db, audit.AuditAction.OFFICIAL_PAGE_DOCUMENT_ADDED, actor_id=actor.id,
        target_type="official_page", target_id=page.id, ip_address=ip,
        details={"sha256": page.document_sha256, "content_type": content_type,
                 "bytes": len(data)},
    )  # fmt: skip


def verify(
    db: Session, page: OfficialPage, method: VerificationMethod, note: str,
    *, actor: User, ip: str | None,
) -> None:  # fmt: skip
    if page.status == PageStatus.SUSPENDED:
        raise OfficialPageError("Reinstate the page instead of verifying it again")
    if method == VerificationMethod.OFFICIAL_EMAIL and not page.contact_email:
        raise OfficialPageError("Add the office's official email address first")
    if method == VerificationMethod.OFFICIAL_LETTER and not page.document_key:
        raise OfficialPageError("Upload the scan of the official letter first")
    page.status = PageStatus.VERIFIED
    page.verification_method, page.verification_note = method, note.strip()
    page.verified_by, page.verified_at = actor, datetime.now(UTC)
    page.suspended_reason = None
    audit.record(
        db, audit.AuditAction.OFFICIAL_PAGE_VERIFIED, actor_id=actor.id,
        target_type="official_page", target_id=page.id, ip_address=ip,
        details={"method": method.value, "note": page.verification_note,
                 "contact_email": page.contact_email, "document_sha256": page.document_sha256},
    )  # fmt: skip


def suspend(db: Session, page: OfficialPage, reason: str, *, actor: User, ip: str | None):
    if page.status == PageStatus.SUSPENDED:
        raise OfficialPageError("The page is already suspended")
    page.status, page.suspended_reason = PageStatus.SUSPENDED, reason.strip()
    audit.record(
        db, audit.AuditAction.OFFICIAL_PAGE_SUSPENDED, actor_id=actor.id,
        target_type="official_page", target_id=page.id, ip_address=ip,
        details={"reason": page.suspended_reason},
    )  # fmt: skip


def reinstate(db: Session, page: OfficialPage, *, actor: User, ip: str | None):
    if page.status != PageStatus.SUSPENDED:
        raise OfficialPageError("Only a suspended page can be reinstated")
    if page.verified_at is None:
        page.status = PageStatus.PENDING  # was never verified: back to waiting
    else:
        page.status = PageStatus.VERIFIED
    page.suspended_reason = None
    audit.record(
        db, audit.AuditAction.OFFICIAL_PAGE_REINSTATED, actor_id=actor.id,
        target_type="official_page", target_id=page.id, ip_address=ip,
        details={"status": page.status.value},
    )  # fmt: skip
