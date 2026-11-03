"""Cricket-aware extraction. Pure/offline: given page content, it surfaces candidate signals and
asserts nothing. Verifies honesty rules (unknown stays unknown; confidence is a capped hint)."""
from __future__ import annotations

from onestats.domain.research import webextract
from onestats.domain.research.webextract import KIND_OTHER, KIND_SCORECARD, extract

SCORECARD_HTML = """
<html><head><title>Rhymney v Moyston, 14 Jan 1905</title></head><body>
<h1>Rhymney v Moyston</h1>
<p>Played Saturday 14 January 1905. Rhymney 112 all out, Moyston 98.</p>
<pre>
J Smith c Jones b Brown 34
A Walker not out 21
T Bonner lbw b Green 7
R Davies run out 2
</pre>
<p>Rhymney won by 14 runs.</p>
</body></html>
"""

REPORT_HTML = """
<html><head><title>District Cricket Notes</title></head><body>
<p>A keenly contested match of cricket was played on the weekend, with several fine innings and
tight bowling throughout the afternoon.</p>
</body></html>
"""

IRRELEVANT_HTML = "<html><head><title>Weather</title></head><body><p>Sunny tomorrow, 25 degrees.</p></body></html>"


def test_scorecard_is_detected_and_has_signals() -> None:
    e = extract("https://example.com/m", SCORECARD_HTML, context={"club": "Rhymney"})
    assert e.cricket_relevant is True
    assert e.kind == KIND_SCORECARD
    assert e.candidate["observed_scores"]           # "112 all out" / "98"
    assert e.candidate["observed_teams"] == ["Rhymney", "Moyston"]
    assert any("1905" in d for d in e.candidate["observed_dates"])
    assert e.candidate["scorecard_lines"]           # the dismissal-style lines
    assert "Rhymney" in (e.candidate["context_names_present"] or [])


def test_confidence_is_capped_and_optional() -> None:
    e = extract("https://example.com/m", SCORECARD_HTML)
    assert e.confidence is not None and 0.0 < e.confidence <= 0.9   # never certainty
    irrelevant = extract("https://example.com/w", IRRELEVANT_HTML)
    assert irrelevant.confidence is None            # too weak to score → unknown, not 0


def test_irrelevant_page_asserts_nothing() -> None:
    e = extract("https://example.com/w", IRRELEVANT_HTML)
    assert e.cricket_relevant is False
    assert e.kind == KIND_OTHER
    assert e.candidate["observed_scores"] is None   # unknown stays unknown (None), not []/0
    assert e.candidate["observed_teams"] is None


def test_report_prose_classified_relevantly() -> None:
    e = extract("https://example.com/r", REPORT_HTML)
    assert e.cricket_relevant is True
    assert e.title == "District Cricket Notes"


def test_text_mode_without_html() -> None:
    e = extract("https://example.com/t", "Rhymney 150 for 6, won by 20 runs.", is_html=False)
    assert e.cricket_relevant is True
    assert e.candidate["observed_scores"]


def _make_pdf(text: str) -> bytes:
    """A real one-page PDF built with reportlab (already a project dependency)."""
    import io
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, text)
    c.showPage()
    c.save()
    return buf.getvalue()


def test_pdf_to_text_round_trip() -> None:
    raw = _make_pdf("Rhymney 112 all out, Moyston 98. Rhymney won by 14 runs.")
    out = webextract.pdf_to_text(raw)
    assert "Rhymney" in out and "won by 14 runs" in out
    # and the extracted PDF text flows through the normal (non-HTML) extractor
    e = extract("https://example.com/r.pdf", out, is_html=False)
    assert e.cricket_relevant is True


def test_pdf_to_text_graceful_without_library(monkeypatch) -> None:
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "pdfplumber":
            raise ImportError("no pdfplumber")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert webextract.pdf_to_text(b"%PDF-1.4 whatever") == ""


def test_extraction_degrades_without_parser(monkeypatch) -> None:
    # Simulate bs4 being unavailable in a stripped build: html_to_text must still return text.
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "bs4":
            raise ImportError("no bs4")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    title, text = webextract.html_to_text("<html><title>T</title><body>Rhymney 112 all out</body></html>")
    assert "Rhymney 112 all out" in text
