"""Phase 10, Stage 10.6 — OCR / text-extraction pipeline.

OCR output is stored separately from the corrected transcription and is never treated as truth; when no
local engine is available the pipeline falls back to manual transcription. A fake engine is injected so
the suite never depends on a Tesseract binary. Rolled back; skipped without a live DB.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import Settings, get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.research import extraction, sources

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def conn():
    eng = create_engine(settings.database_url, future=True)
    with eng.connect() as c:
        trans = c.begin()
        try:
            yield c
        finally:
            trans.rollback()
    eng.dispose()


@pytest.fixture
def store(tmp_path):
    # a Settings pointing at a temp media root; the pipeline uses it only for file storage (not the DB,
    # which is the injected transactional connection)
    return Settings(env="test", db_password=None, media_root=str(tmp_path), _env_file=None)


def _ws(conn, name):
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES (:n,'club') RETURNING id"), {"n": name}).scalar_one()
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a, :u) ON CONFLICT (id) DO NOTHING"),
                 {"a": ACTOR, "u": f"actor-{name}"})
    set_workspace(conn, wid)
    return wid


def _source_with_file(conn, store, wid, raw=b"scan-bytes"):
    s = sources.create_source(conn, wid, ACTOR, title="clipping", source_type="newspaper_clipping")
    from onestats.domain.research import storage
    stored = storage.store_source_file(store, wid, raw, "image/png")
    sources.set_file(conn, wid, ACTOR, s["id"], file_ref=str(stored["file_ref"]),
                     file_sha256=str(stored["file_sha256"]), file_bytes=int(stored["file_bytes"]),
                     content_type="image/png")
    return s["id"]


def test_ocr_with_injected_engine_stores_text_and_confidence(conn, store):
    wid = _ws(conn, "OCR ENGINE")
    sid = _source_with_file(conn, store, wid)

    def fake(_raw):
        return ("RHYMNEY 120 all out  SMITH c Jones b Brown 54", 0.82)

    out = extraction.extract_source(conn, store, wid, ACTOR, sid, engine=fake, engine_version="fake-1")
    assert out["status"] == "done" and out["method"] == "tesseract"
    assert "SMITH" in out["ocr_text"] and out["confidence"] == 0.82
    assert sources.get_source(conn, sid)["ocr_status"] == "done"


def test_no_engine_falls_back_to_manual(conn, store, monkeypatch):
    wid = _ws(conn, "OCR NONE")
    sid = _source_with_file(conn, store, wid)
    # deterministically simulate "no local OCR engine installed" regardless of the dev/CI machine
    monkeypatch.setattr(extraction, "default_engine", lambda: (None, None))
    out = extraction.extract_source(conn, store, wid, ACTOR, sid)
    assert out["status"] == "manual" and out["method"] == "none" and out["ocr_text"] is None
    assert sources.get_source(conn, sid)["ocr_status"] == "manual"


def test_correction_keeps_machine_text_separate(conn, store):
    wid = _ws(conn, "OCR CORRECT")
    sid = _source_with_file(conn, store, wid)

    def fake(_raw):
        return ("RHYMNEY l2O all 0ut", 0.4)  # poor OCR

    ext = extraction.extract_source(conn, store, wid, ACTOR, sid, engine=fake)
    corrected = extraction.set_correction(conn, wid, ACTOR, ext["id"], "RHYMNEY 120 all out")
    assert corrected["ocr_text"] == "RHYMNEY l2O all 0ut"        # machine text preserved verbatim
    assert corrected["corrected_text"] == "RHYMNEY 120 all out"  # researcher correction stored alongside


def test_manual_transcription_without_ocr(conn, store):
    wid = _ws(conn, "OCR MANUAL")
    s = sources.create_source(conn, wid, ACTOR, title="handwritten book", source_type="handwritten_scorecard")
    out = extraction.record_manual(conn, wid, ACTOR, s["id"], text_value="Innings of Moyston, 1897")
    assert out["method"] == "manual" and out["corrected_text"].startswith("Innings of Moyston")


def test_scorecard_line_hint():
    text_in = "Preview of the big match\nSMITH c Jones b Brown 54\nThe weather was fine\nExtras 11  Total 231"
    hints = extraction.likely_scorecard_lines(text_in)
    assert any("SMITH" in h for h in hints)
    assert "The weather was fine" not in hints


def test_preprocess_grayscales_and_upscales():
    # No DB or Tesseract binary needed — pure Pillow image handling.
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (120, 50), "white").save(buf, "JPEG")
    out = extraction._preprocess(buf.getvalue())
    assert out.mode == "L"            # OCR runs on grayscale
    assert max(out.size) >= 240       # small scans are upscaled (120 -> >=240)


def test_preprocess_coerces_exotic_mode():
    # A palette-mode ('P') image must be coerced to a safe mode rather than raising — this mirrors the
    # phone-camera MPO/CMYK sources that previously made OCR fail silently.
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("P", (130, 60)).save(buf, "PNG")
    out = extraction._preprocess(buf.getvalue())
    assert out.mode == "L"
