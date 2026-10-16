import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.statement import Finding
from app.schemas.statement import EventLite, PageLite


class Signup(BaseModel):
    email: str = Field(max_length=320)
    display_name: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=10, max_length=256)


class Login(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)


class VerifyEmail(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class PasswordConfirm(BaseModel):
    password: str = Field(max_length=256)


class PublicToken(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 (the OAuth token type, not a secret)
    expires_in: int


class Me(BaseModel):
    id: uuid.UUID
    display_name: str
    email: str


class CommentCreate(BaseModel):
    body: str = Field(min_length=2, max_length=1000)


class OpinionCreate(BaseModel):
    body: str = Field(min_length=2, max_length=1500)


class PublicOpinion(BaseModel):
    """What one person says about an incident: their own view, not verified."""

    id: uuid.UUID
    author: str
    body: str
    created_at: datetime
    mine: bool = False


class ReportCreate(BaseModel):
    reason: str


class PublicComment(BaseModel):
    id: uuid.UUID
    author: str
    body: str
    created_at: datetime
    mine: bool = False


class PublicPost(BaseModel):
    """An official statement as the public sees it: no brief, no author, just the office."""

    id: uuid.UUID
    page: PageLite
    event: EventLite
    finding: Finding
    title: str
    body: str
    published_at: datetime
    supersedes_id: uuid.UUID | None
    superseded_by_id: uuid.UUID | None
    likes: int
    comments: int
    liked: bool


class PublicPostDetail(PublicPost):
    comment_list: list[PublicComment]


class PublicPage(BaseModel):
    page: PageLite
    description: str | None
    website: str | None
    verified_at: datetime | None
    posts: list[PublicPost]


class Incident(BaseModel):
    event: EventLite
    posts: list[PublicPost]
    opinions: list[PublicOpinion]


class ModerationComment(BaseModel):
    """A comment on an official post, or (kind "opinion") an opinion on an incident, in
    which case statement_id is the incident's event id and statement_title its title."""

    kind: str = "comment"
    id: uuid.UUID
    statement_id: uuid.UUID
    statement_title: str
    page_name: str
    author: str
    account_id: uuid.UUID
    account_status: str
    body: str
    created_at: datetime
    reports: int
    report_reasons: list[str]
    hidden_at: datetime | None
    hidden_reason: str | None


class Reason(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
