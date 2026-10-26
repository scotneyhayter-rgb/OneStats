"""Secret-at-rest encryption for per-workspace API/integration credentials.

API secrets (keys/tokens) are encrypted with Fernet (AES-128-CBC + HMAC) before they are stored in the
database, using a key kept **outside** the database (``ONESTATS_ENCRYPTION_KEY`` — env var / OS keystore).
``MultiFernet`` supports **key rotation**: the first key encrypts, any configured key can decrypt, so a new
key can be rolled in and old ciphertext re-encrypted without downtime. Plaintext secrets never touch the DB
and are never logged. When no key is configured a clearly-marked **development** key is derived and a
warning is logged — production must set a real key (the installer/operator does, kept separate from the DB).
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import InvalidToken, MultiFernet

from onestats.core.config import Settings, get_settings
from onestats.core.logging import get_logger

log = get_logger("onestats.crypto")

_DEV_WARNED = False


def _dev_key() -> str:
    # a deterministic, clearly-insecure development key (NOT for production) so dev/tests work without setup
    digest = hashlib.sha256(b"onestats-development-encryption-key-not-for-production").digest()
    return base64.urlsafe_b64encode(digest).decode()


def _fernet(settings: Settings | None = None) -> MultiFernet:
    global _DEV_WARNED
    s = settings or get_settings()
    raw = (s.encryption_key or "").strip()
    if not raw:
        if not _DEV_WARNED:
            log.warning("No ONESTATS_ENCRYPTION_KEY set — using an INSECURE development key. Set a real "
                        "key (kept outside the database) in production.")
            _DEV_WARNED = True
        keys = [_dev_key()]
    else:
        keys = [k.strip() for k in raw.split(",") if k.strip()]
    from cryptography.fernet import Fernet
    return MultiFernet([Fernet(k.encode()) for k in keys])


def encrypt(plaintext: str, settings: Settings | None = None) -> str:
    """Encrypt a secret for storage. Returns a URL-safe ciphertext token (never the plaintext)."""
    return _fernet(settings).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str, settings: Settings | None = None) -> str:
    """Decrypt a stored ciphertext token. Raises ValueError if it cannot be decrypted with any key."""
    try:
        return _fernet(settings).decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise ValueError("cannot_decrypt_secret") from exc


def rotate(token: str, settings: Settings | None = None) -> str:
    """Re-encrypt an existing ciphertext under the current (first) key — for key rotation."""
    return _fernet(settings).rotate(token.encode("ascii")).decode("ascii")


def new_key() -> str:
    """Generate a fresh Fernet key (for operators setting/rotating ONESTATS_ENCRYPTION_KEY)."""
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode("ascii")
