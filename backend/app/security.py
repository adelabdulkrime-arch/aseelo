"""Password hashing and JWT issuing/verification."""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.config import settings

_BCRYPT_ROUNDS = 12


def _prepare(password: str) -> bytes:
    """Normalise an arbitrary-length password into 44 bytes for bcrypt.

    bcrypt silently truncates input at 72 bytes, which is easy to hit with
    multi-byte (e.g. Arabic) passwords. Pre-hashing with SHA-256 and
    base64-encoding keeps the full entropy of long passwords - the same
    approach used by passlib's ``bcrypt_sha256`` scheme.
    """
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str | uuid.UUID,
    *,
    role: str = "USER",
    expires_minutes: int | None = None,
) -> str:
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


# ---------------------------------------------------------------------------
# Password reset tokens
# ---------------------------------------------------------------------------
def generate_reset_token() -> tuple[str, str]:
    """Return ``(plaintext, sha256_hex)`` for a fresh reset token.

    The plaintext goes in the email and is never persisted; the digest is what
    the database stores and what a redemption is looked up by. SHA-256 without
    a salt is deliberate here and safe: unlike a password this is 256 bits of
    CSPRNG output, so it is not guessable and a slow KDF would buy nothing
    while making every redemption expensive.
    """
    plaintext = secrets.token_urlsafe(32)
    return plaintext, hash_reset_token(plaintext)


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired or has a bad signature."""


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Invalid token") from exc

    if payload.get("type") != "access":
        raise TokenError("Invalid token type")
    return payload
