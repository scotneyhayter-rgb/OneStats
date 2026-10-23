"""Security primitives: password hashing (Argon2id) and opaque session tokens.

Passwords are hashed with Argon2id (D25). Session/setup tokens are high-entropy random
strings; only their SHA-256 hash is stored, so a database leak does not expose usable
tokens. No secret is ever logged.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_ph = PasswordHasher()  # Argon2id with sensible defaults


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _ph.verify(stored_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(stored_hash: str) -> bool:
    try:
        return _ph.check_needs_rehash(stored_hash)
    except Exception:  # noqa: BLE001 - fail safe: treat any parsing issue as needing rehash
        return True


def generate_token() -> str:
    """A new opaque, URL-safe token (~256 bits of entropy)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 of a token for storage/lookup (tokens are already high-entropy)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_equal(a: str, b: str) -> bool:
    """Constant-time comparison for token hashes."""
    return hmac.compare_digest(a, b)
