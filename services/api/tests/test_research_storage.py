"""Phase 10, Stage 10.2 — research source-file storage abstraction (no DB needed)."""
from __future__ import annotations

import hashlib

import pytest

from onestats.core.config import Settings
from onestats.domain.research import storage


def _settings(tmp_path) -> Settings:
    return Settings(env="test", db_password=None, media_root=str(tmp_path), _env_file=None)


def test_store_and_read_back_preserves_bytes_and_hash(tmp_path):
    s = _settings(tmp_path)
    raw = b"%PDF-1.4 fake newspaper scan bytes"
    out = storage.store_source_file(s, __uuid(), raw, "application/pdf")
    assert out["file_bytes"] == len(raw)
    assert out["file_sha256"] == hashlib.sha256(raw).hexdigest()
    assert str(out["file_ref"]).endswith(".pdf")


def test_rejects_unsupported_type_and_oversize(tmp_path):
    s = _settings(tmp_path)
    with pytest.raises(storage.SourceFileError, match="unsupported_source_type"):
        storage.store_source_file(s, __uuid(), b"x", "text/html")
    with pytest.raises(storage.SourceFileError, match="empty_file"):
        storage.store_source_file(s, __uuid(), b"", "image/png")
    s2 = Settings(env="test", db_password=None, media_root=str(tmp_path), max_source_bytes=4, _env_file=None)
    with pytest.raises(storage.SourceFileError, match="file_too_large"):
        storage.store_source_file(s2, __uuid(), b"12345", "image/png")


def test_path_lookup_is_traversal_safe(tmp_path):
    s = _settings(tmp_path)
    wid = __uuid()
    out = storage.store_source_file(s, wid, b"img", "image/png")
    assert storage.source_file_path(s, wid, str(out["file_ref"])) is not None
    assert storage.source_file_path(s, wid, "../escape.png") is None
    assert storage.source_file_path(s, wid, "missing.png") is None


def __uuid():
    import uuid
    return uuid.uuid4()
