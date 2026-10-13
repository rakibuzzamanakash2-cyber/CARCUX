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
