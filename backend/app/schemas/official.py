import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.official import PageKind, PageStatus, VerificationMethod
from app.schemas.user import UserCreate


class OfficialPageCreate(BaseModel):
    slug: str = Field(min_length=3, max_length=60, description="Address of the page: /pages/<slug>")
    name: str = Field(min_length=3, max_length=200)
    name_bn: str | None = Field(default=None, max_length=200)
    kind: PageKind
    description: str | None = Field(default=None, max_length=2000)
    website: HttpUrl | None = None
    contact_email: str | None = Field(
        default=None, max_length=320, description="The office's own address, e.g. info@pmo.gov.bd"
    )


class OfficialPageUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=200)
    name_bn: str | None = Field(default=None, max_length=200)
    kind: PageKind | None = None
    description: str | None = Field(default=None, max_length=2000)
    website: HttpUrl | None = None
    contact_email: str | None = Field(default=None, max_length=320)


class Verification(BaseModel):
    method: VerificationMethod
    note: str = Field(
        min_length=10,
        max_length=2000,
        description="What was checked: who confirmed, from which address, letter reference",
    )


class Suspension(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


class MemberCreate(BaseModel):
    email: str
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=256)

    def as_user(self, page_id: uuid.UUID) -> UserCreate:
        return UserCreate(
            email=self.email, full_name=self.full_name, password=self.password,
            role="official", official_page_id=page_id,
        )  # fmt: skip


class Person(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str


class Member(Person):
    email: str
    is_active: bool
    last_login_at: datetime | None


class OfficialPageRead(BaseModel):
    """What everyone signed in sees of a page."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    name_bn: str | None
    kind: PageKind
    description: str | None
    website: str | None
    status: PageStatus
    verification_method: VerificationMethod | None
    verified_at: datetime | None


class OfficialPageDetail(OfficialPageRead):
    """Admins and the page's own officials: how it was verified, and who speaks for it."""

    contact_email: str | None
    verification_note: str | None
    verified_by: Person | None
    has_document: bool
    document_type: str | None
    document_sha256: str | None
    suspended_reason: str | None
    created_at: datetime
    members: list[Member]
