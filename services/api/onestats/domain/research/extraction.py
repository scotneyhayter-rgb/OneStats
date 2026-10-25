"""OCR & historical text extraction (Phase 10, Stage 10.6).

Local-first and honest about uncertainty. A pluggable OCR engine turns a source image/PDF page into
machine text with a confidence; when no local engine is available the pipeline falls back to manual
transcription rather than claiming a capability it does not have. OCR output is stored separately from
the researcher's corrected transcription and is never treated as verified truth. No paid cloud OCR is
used — introducing one would require explicit user approval.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.core.config import Settings
from onestats.domain import audit
from onestats.domain.research import sources, storage

# An OCR engine: raw document bytes -> (text, confidence 0..1 or None). Returns None when unavailable.
OcrEngine = Callable[[bytes], "tuple[str, float | None]"]


class OcrUnavailable(RuntimeError):
    """No local OCR engine is installed; manual transcription is the fallback."""


def default_engine() -> tuple[OcrEngine | None, str | None]:
    """Detect a local OCR engine (Tesseract via pytesseract). Returns (engine, version) or (None, None).

    Never imports a paid cloud provider. The import is lazy so a missing binary/package is a graceful
    fallback, not an import error at startup."""
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except Exception:  # noqa: BLE001 - any import/env problem means "no engine", fall back gracefully
        return None, None
    try:
        version = str(pytesseract.get_tesseract_version())
    except Exception:  # noqa: BLE001 - a missing/broken Tesseract binary means "no engine"
        return None, None

    def _engine(raw: bytes) -> tuple[str, float | None]:
        import io

        img = Image.open(io.BytesIO(raw))
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        words = [w for w in data.get("text", []) if w and w.strip()]
        confs = [int(c) for c in data.get("conf", []) if str(c).lstrip("-").isdigit() and int(c) >= 0]
        text_out = " ".join(words)
        conf = (sum(confs) / len(confs) / 100.0) if confs else None
        return text_out, conf

    return _engine, f"tesseract {version}"


# Heuristic: lines that look like scorecard entries (a name followed by a number, or b/c/lbw/run out).
_DISMISSAL_HINTS = ("c ", "b ", "lbw", "run out", "st ", "not out", "retired", "did not bat")


def likely_scorecard_lines(text_in: str) -> list[str]:
    """Flag lines that plausibly contain scorecard data, to help the researcher locate figures. This is
    a hint only — it never extracts or asserts values on its own."""
    out: list[str] = []
    for line in (text_in or "").splitlines():
        low = line.lower()
        has_number = any(ch.isdigit() for ch in line)
        if has_number and (any(h in low for h in _DISMISSAL_HINTS) or sum(c.isdigit() for c in line) >= 2):
            out.append(line.strip())
    return out


def _get_extraction(conn: Connection, extraction_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text("SELECT * FROM source_extraction WHERE id = :id"), {"id": extraction_id}).mappings().first()
    return dict(r) if r else None


def list_for_source(conn: Connection, workspace_id: UUID, source_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT * FROM source_extraction WHERE workspace_id = :w AND source_id = :s ORDER BY page"),
        {"w": workspace_id, "s": source_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def _upsert(conn: Connection, workspace_id: UUID, source_id: UUID, page: int, *, method: str,
            method_version: str | None, ocr_text: str | None, confidence: float | None,
            status: str, language: str | None = None) -> UUID:
    return conn.execute(
        text("INSERT INTO source_extraction(workspace_id, source_id, page, method, method_version, ocr_text, "
             "confidence, language, status) VALUES (:w, :s, :pg, :m, :mv, :ot, :cf, :lg, :st) "
             "ON CONFLICT ON CONSTRAINT uq_source_extraction_page DO UPDATE SET "
             "method = :m, method_version = :mv, ocr_text = :ot, confidence = :cf, language = :lg, "
             "status = :st, updated_at = now() RETURNING id"),
        {"w": workspace_id, "s": source_id, "pg": page, "m": method, "mv": method_version, "ot": ocr_text,
         "cf": confidence, "lg": language, "st": status},
    ).scalar_one()


def extract_source(conn: Connection, settings: Settings, workspace_id: UUID, actor: str, source_id: UUID,
                   *, page: int = 1, engine: OcrEngine | None = None, engine_version: str | None = None,
                   language: str | None = None) -> dict[str, Any]:
    """Run OCR on a source's stored document. With no engine available, records a manual-transcription
    placeholder (status 'manual') instead of pretending to have read the page."""
    src = sources.get_source(conn, source_id)
    if src is None:
        raise ValueError("source_not_found")
    if not src.get("file_ref"):
        raise ValueError("no_file")

    if engine is None:
        engine, engine_version = default_engine()

    if engine is None:
        eid = _upsert(conn, workspace_id, source_id, page, method="none", method_version=None,
                      ocr_text=None, confidence=None, status="manual", language=language)
        conn.execute(text("UPDATE research_source SET ocr_status = 'manual', updated_at = now() WHERE id = :id"),
                     {"id": source_id})
        audit.write_audit(conn, workspace_id, actor, "research.ocr_unavailable", entity="source_extraction",
                          entity_id=str(eid), after={"page": page})
        return _get_extraction(conn, eid)

    path = storage.source_file_path(settings, workspace_id, src["file_ref"])
    if path is None:
        raise ValueError("no_file")
    raw = path.read_bytes()
    try:
        ocr_text, confidence = engine(raw)
        status = "done"
    except Exception:  # noqa: BLE001 - OCR engines raise many error types; a failure is recorded, not fatal
        ocr_text, confidence, status = None, None, "failed"
    eid = _upsert(conn, workspace_id, source_id, page, method="tesseract", method_version=engine_version,
                  ocr_text=ocr_text, confidence=confidence, status=status, language=language)
    conn.execute(text("UPDATE research_source SET ocr_status = :st, updated_at = now() WHERE id = :id"),
                 {"st": "done" if status == "done" else "failed", "id": source_id})
    audit.write_audit(conn, workspace_id, actor, "research.ocr_extracted", entity="source_extraction",
                      entity_id=str(eid), after={"page": page, "status": status, "confidence": confidence})
    return _get_extraction(conn, eid)


def set_correction(conn: Connection, workspace_id: UUID, actor: str, extraction_id: UUID,
                   corrected_text: str) -> dict[str, Any]:
    """Save a researcher's corrected transcription. The machine OCR text is kept untouched alongside it."""
    ext = _get_extraction(conn, extraction_id)
    if ext is None:
        raise ValueError("extraction_not_found")
    conn.execute(
        text("UPDATE source_extraction SET corrected_text = :ct, status = 'done', updated_at = now() WHERE id = :id"),
        {"ct": corrected_text, "id": extraction_id},
    )
    conn.execute(text("UPDATE research_source SET ocr_status = 'done', updated_at = now() WHERE id = :id"),
                 {"id": ext["source_id"]})
    audit.write_audit(conn, workspace_id, actor, "research.transcription_corrected", entity="source_extraction",
                      entity_id=str(extraction_id), after={"chars": len(corrected_text or "")})
    return _get_extraction(conn, extraction_id)


def record_manual(conn: Connection, workspace_id: UUID, actor: str, source_id: UUID, *, text_value: str,
                  page: int = 1) -> dict[str, Any]:
    """Record a manual transcription directly (no OCR), e.g. for handwritten material."""
    eid = _upsert(conn, workspace_id, source_id, page, method="manual", method_version=None,
                  ocr_text=None, confidence=None, status="done")
    conn.execute(text("UPDATE source_extraction SET corrected_text = :ct WHERE id = :id"),
                 {"ct": text_value, "id": eid})
    conn.execute(text("UPDATE research_source SET ocr_status = 'manual', updated_at = now() WHERE id = :id"),
                 {"id": source_id})
    audit.write_audit(conn, workspace_id, actor, "research.manual_transcription", entity="source_extraction",
                      entity_id=str(eid), after={"page": page})
    return _get_extraction(conn, eid)
