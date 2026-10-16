import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.security import MIN_PASSWORD_LENGTH
from app.models.user import Role
from app.services.users import normalise_email


class UserCreate(BaseModel):
    email: str
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)
    role: Role
    # Required for officials (the page they speak for), refused for anyone else.
    official_page_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _official_has_page(self) -> "UserCreate":
        if (self.role == Role.OFFICIAL) != (self.official_page_id is not None):
            raise ValueError("An official account needs its official page, and only officials")
        return self

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        return normalise_email(value)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: Role | None = None
    is_active: bool | None = None
    official_page_id: uuid.UUID | None = None


class OfficialPageRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    status: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None
    official_page: OfficialPageRef | None = None


class AccountRiskRead(BaseModel):
    """How unlike its own history a field worker's last day looks. For a conversation
    with the worker, never an automatic block."""

    user_id: uuid.UUID
    full_name: str
    score: float  # 0 (as usual) to 1
    parts: dict[str, float]
    reasons: list[str]
    recent: int  # reports in the last 24 hours
    baseline: int  # earlier reports it is compared with
