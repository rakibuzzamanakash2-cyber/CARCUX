from datetime import datetime

from pydantic import BaseModel, Field

from app.core.security import MIN_PASSWORD_LENGTH


class LoginRequest(BaseModel):
    # Not format-checked: login only looks the account up. Any account that exists
    # must be able to log in, whatever rule was in force when it was created.
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)  # bounds Argon2 work per request


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105  (OAuth2 token type, not a secret)
    expires_in: int


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)


class LoginResult(BaseModel):
    """A token, or (for an account with two-factor sign-in) a challenge to answer at
    POST /auth/login/two-factor with a code."""

    access_token: str | None = None
    token_type: str = "bearer"  # noqa: S105  (OAuth2 token type, not a secret)
    expires_in: int
    two_factor_required: bool = False
    challenge: str | None = None


class TwoFactorLogin(BaseModel):
    challenge: str = Field(max_length=2000)
    code: str = Field(min_length=6, max_length=20)  # 6 digits, or a recovery code


class TwoFactorSetup(BaseModel):
    secret: str  # for typing in by hand
    otpauth_uri: str
    qr_svg: str


class TwoFactorCode(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class TwoFactorDisable(BaseModel):
    password: str = Field(max_length=256)
    code: str = Field(min_length=6, max_length=20)


class RecoveryCodes(BaseModel):
    recovery_codes: list[str]  # shown once


class TwoFactorStatus(BaseModel):
    enabled: bool
    enabled_at: datetime | None
    recovery_codes_left: int
    required: bool  # the account's role must use it
