import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("a long enough password")

    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "a long enough password")
    assert not verify_password(hashed, "wrong password")


def test_unknown_account_never_verifies():
    assert not verify_password(None, "anything")


def test_token_roundtrip():
    settings = Settings(environment="test")
    user_id = uuid.uuid4()
    token, lifetime = create_access_token(settings, user_id, "analyst", 3)

    claims = decode_access_token(settings, token)
    assert claims.user_id == user_id
    assert claims.role == "analyst"
    assert claims.token_version == 3
    assert lifetime == settings.access_token_minutes * 60


def test_token_signed_with_other_secret_is_rejected():
    token, _ = create_access_token(
        Settings(environment="test", jwt_secret="a" * 40), uuid.uuid4(), "admin", 0
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(Settings(environment="test", jwt_secret="b" * 40), token)


def test_expired_token_is_rejected():
    settings = Settings(environment="test")
    past = datetime.now(UTC) - timedelta(hours=1)
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "ver": 0, "type": "access", "iat": past, "exp": past},
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(settings, token)


def test_unsigned_token_is_rejected():
    settings = Settings(environment="test")
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "ver": 0, "type": "access", "iat": now, "exp": now},
        key=None,
        algorithm="none",
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(settings, token)


def test_production_refuses_default_secret():
    with pytest.raises(ValidationError):
        Settings(environment="production")
    with pytest.raises(ValidationError):
        Settings(environment="production", jwt_secret="too-short")
    assert Settings(environment="production", jwt_secret="z" * 40)
