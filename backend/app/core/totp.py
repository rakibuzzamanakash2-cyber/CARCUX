"""Two-factor sign-in with an authenticator app (TOTP, RFC 6238) and recovery codes.

- Codes: 6 digits, SHA-1, 30-second steps (what Google Authenticator, Microsoft
  Authenticator, Aegis and others expect). One step either side is accepted for clock
  drift, and a step that was used once is refused after that (no replay).
- Secrets are kept encrypted (AES-GCM) with a key derived from the server's JWT secret,
  so a copy of the database alone does not give them away. Changing the JWT secret
  makes existing secrets unreadable: two-factor must then be set up again.
- Recovery codes: 10 random codes shown once; only keyed hashes are stored, and each
  works once.
"""

import base64
import hashlib
import hmac
import io
import os
import secrets
import struct
from urllib.parse import quote

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import Settings

STEP = 30
DIGITS = 6
WINDOW = 1  # steps accepted either side of now
ISSUER = "CARCUX"
RECOVERY_CODES = 10


def new_secret() -> str:
    """A 160-bit secret in base32, as authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(settings: Settings) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"carcux-totp-secrets"
    ).derive(settings.jwt_secret.get_secret_value().encode())


def encrypt(settings: Settings, secret: str) -> str:
    nonce = os.urandom(12)
    sealed = AESGCM(_key(settings)).encrypt(nonce, secret.encode(), b"totp")
    return base64.urlsafe_b64encode(nonce + sealed).decode()


def decrypt(settings: Settings, stored: str) -> str:
    raw = base64.urlsafe_b64decode(stored.encode())
    return AESGCM(_key(settings)).decrypt(raw[:12], raw[12:], b"totp").decode()


def code_at(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def verify(secret: str, code: str, now: float, last_counter: int | None) -> int | None:
    """The time step the code belongs to, or None. A step at or before `last_counter`
    (already used) is refused."""
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != DIGITS:
        return None
    current = int(now // STEP)
    for counter in range(current - WINDOW, current + WINDOW + 1):
        if last_counter is not None and counter <= last_counter:
            continue
        if hmac.compare_digest(code_at(secret, counter), code):
            return counter
    return None


def otpauth_uri(secret: str, account: str) -> str:
    label = quote(f"{ISSUER}:{account}", safe=":@")
    return f"otpauth://totp/{label}?secret={secret}&issuer={ISSUER}&algorithm=SHA1&digits={DIGITS}&period={STEP}"


def qr_svg(uri: str) -> str:
    import segno

    out = io.BytesIO()
    segno.make(uri, error="m").save(out, kind="svg", scale=5, border=2, dark="#0b2a1c")
    return out.getvalue().decode()


def recovery_codes() -> list[str]:
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i
    return ["-".join("".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(2))
            for _ in range(RECOVERY_CODES)]  # fmt: skip


def recovery_hash(settings: Settings, code: str) -> str:
    normal = code.strip().lower().replace(" ", "")
    return hmac.new(_key(settings), normal.encode(), hashlib.sha256).hexdigest()
