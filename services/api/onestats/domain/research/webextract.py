"""Cricket-aware extraction from fetched web pages (Internet Research Engine).

Turns the UNTRUSTED text/HTML returned by :mod:`webfetch` into a structured *candidate* — a set of
observed signals (title, dates, team-like names, score-like figures, likely scorecard lines) that MAY
describe a cricket match. It asserts nothing: every field is optional and absent/unknown when the page
does not clearly provide it ("unknown" is never coerced to zero or to a guess). The output is evidence
for a human to review, tagged with the source URL — not a statistic and never auto-applied.

The fetched content is treated purely as data. No instruction-like text in a page is ever acted on;
this module only reads and pattern-matches, and reuses the Phase 10 ``extraction.likely_scorecard_lines``
heuristic so the same honest "this line *looks* like scorecard data" signal is used everywhere.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from onestats.domain.research import extraction

# Finding kinds mirror research_finding.kind (migration 0065).
KIND_SCORECARD = "scorecard"
KIND_RESULT = "result"
KIND_REPORT = "report"
KIND_PLAYER = "player_info"
KIND_NEWSPAPER = "newspaper"
KIND_MATCH = "match_candidate"
KIND_OTHER = "other"

_CRICKET_TERMS = (
    "cricket", "wicket", "wickets", "innings", "batting", "bowling", "overs", "run out", "not out",
    "lbw", "caught", "bowled", "stumped", "maiden", "boundary", "all out", "declared", "scorecard",
    "won by", "runs", "partnership", "dismissed",
)
_RESULT_PHRASES = ("won by", "lost by", "match drawn", "match tied", "no result", "abandoned",
                   "beat", "defeated")
# A score like "123/4", "123 for 4", "123 all out", "98 (34.2 overs)".
_SCORE_RE = re.compile(r"\b(\d{1,3})\s*(?:/|for|-)\s*(\d{1,2})\b|\b(\d{1,3})\s+all out\b", re.IGNORECASE)
# A date like "6 November 1931", "Nov 1931", "1931", "14/01/1905".
_DATE_RE = re.compile(
    r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}"
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|\b(?:18|19|20)\d{2})\b",
    re.IGNORECASE,
)
# "<Team A> v[s] <Team B>" — team-like names around a versus token.
_VERSUS_RE = re.compile(r"([A-Z][\w&'. ]{1,40}?)\s+(?:v\.?|vs\.?|versus)\s+([A-Z][\w&'. ]{1,40})")


@dataclass(slots=True)
class Extraction:
    kind: str
    title: str | None = None
    summary: str | None = None
    confidence: float | None = None          # hint only; None when too weak to score
    candidate: dict[str, Any] = field(default_factory=dict)
    raw_excerpt: str | None = None
    cricket_relevant: bool = False


def pdf_to_text(raw: bytes, *, max_pages: int = 20) -> str:
    """Extract text from a PDF's bytes using pdfplumber (lazy import). Returns "" when the library is
    unavailable or the PDF has no extractable text layer (e.g. a pure scan — that path is OCR's job),
    so the pipeline degrades gracefully and never crashes on a binary body."""
    try:
        import pdfplumber  # lazy: packaged build may resolve it late / not at all
    except Exception:  # noqa: BLE001 - no pdf library: degrade to no text
        return ""
    import io

    out: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for page in pdf.pages[:max_pages]:
                try:
                    out.append(page.extract_text() or "")
                except Exception:  # noqa: BLE001 - a bad page must not abort the whole document
                    continue
    except Exception:  # noqa: BLE001 - corrupt/encrypted PDF: no text, not a crash
        return ""
    return _normalise_lines("\n".join(out))


def _normalise_lines(text: str) -> str:
    """Collapse spaces/tabs within lines but preserve line breaks (line structure matters for the
    scorecard-line heuristic). Drops blank lines."""
    lines = []
    for raw in (text or "").splitlines():
        line = re.sub(r"[ \t ]+", " ", raw).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def html_to_text(html: str) -> tuple[str | None, str]:
    """Return (title, visible_text). Uses BeautifulSoup+lxml (lazy import); falls back to a crude tag
    strip if the parser is unavailable so extraction still degrades gracefully."""
    try:
        from bs4 import BeautifulSoup  # lazy: packaged build may resolve it late
    except Exception:  # noqa: BLE001 - no parser: degrade, never crash
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
        text = re.sub(r"(?s)<[^>]+>", "\n", text)
        return None, _normalise_lines(text)
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:  # noqa: BLE001 - malformed markup: fall back to the forgiving builtin parser
        soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    elif soup.find("h1"):
        title = soup.find("h1").get_text(" ", strip=True)
    # Keep line structure (newline separator) so line-based scorecard detection works; collapse only
    # runs of spaces/tabs within each line.
    text = _normalise_lines(soup.get_text("\n"))
    return title, text


def _classify(text_lower: str, scorecard_lines: list[str]) -> str:
    if len(scorecard_lines) >= 4:
        return KIND_SCORECARD
    if any(p in text_lower for p in _RESULT_PHRASES) and any(t in text_lower for t in ("cricket", "wicket", "runs", "overs")):
        return KIND_RESULT
    if _VERSUS_RE.search(text_lower[:2000]) or ("scorecard" in text_lower):
        return KIND_MATCH
    if any(t in text_lower for t in ("batting average", "bowling average", "career", "profile")):
        return KIND_PLAYER
    return KIND_OTHER


def _score_confidence(cricket_terms_hit: int, has_date: bool, has_score: bool,
                      scorecard_lines: int, has_versus: bool) -> float | None:
    """A modest, capped relevance hint — NOT a claim of correctness. None when the page shows almost no
    cricket signal."""
    if cricket_terms_hit == 0 and not has_score and not has_versus:
        return None
    score = 0.0
    score += min(cricket_terms_hit, 6) * 0.07   # up to 0.42
    score += 0.12 if has_date else 0.0
    score += 0.12 if has_score else 0.0
    score += 0.10 if has_versus else 0.0
    score += min(scorecard_lines, 6) * 0.04     # up to 0.24
    return round(min(score, 0.9), 3)            # never 1.0 — extraction is never certainty


def extract(url: str, content: str, *, title_hint: str | None = None,
            is_html: bool = True, context: dict[str, Any] | None = None) -> Extraction:
    """Extract a cricket candidate from one page's content. ``context`` (club/season/competition/etc.)
    is used only to help spot relevant names — it never fills in values the page does not contain."""
    if is_html:
        title, text = html_to_text(content)
    else:
        title, text = None, re.sub(r"\s+", " ", content or "").strip()
    title = title or title_hint
    low = text.lower()

    terms_hit = sum(1 for t in _CRICKET_TERMS if t in low)
    scorecard_lines = extraction.likely_scorecard_lines(text)
    dates = _DATE_RE.findall(text)
    # findall on the date alternation returns tuples/strings depending on groups; normalise to strings.
    dates = [d if isinstance(d, str) else next((g for g in d if g), "") for d in dates]
    dates = [d.strip() for d in dates if d and d.strip()]
    scores_raw = _SCORE_RE.findall(text)
    scores = [" ".join(p for p in grp if p) for grp in scores_raw] if scores_raw else []
    versus = _VERSUS_RE.search(text)
    teams = [versus.group(1).strip(), versus.group(2).strip()] if versus else []

    cricket_relevant = terms_hit >= 2 or bool(scores) or bool(versus) or len(scorecard_lines) >= 2
    kind = _classify(low, scorecard_lines) if cricket_relevant else KIND_OTHER
    confidence = _score_confidence(terms_hit, bool(dates), bool(scores), len(scorecard_lines), bool(versus))

    # Context-mentioned names actually present on the page (helps a reviewer judge relevance). We only
    # REPORT which known names appear; we never assert the page is about them.
    mentioned: list[str] = []
    for key in ("club", "team", "opponent", "competition", "player"):
        val = (context or {}).get(key)
        if isinstance(val, str) and val and val.lower() in low:
            mentioned.append(val)

    candidate: dict[str, Any] = {
        # every field is an OBSERVATION from this one source, not a verified value; unknown => omitted/None
        "observed_title": title,
        "observed_dates": dates[:8] or None,
        "observed_teams": teams or None,
        "observed_scores": scores[:12] or None,
        "scorecard_lines": scorecard_lines[:20] or None,
        "context_names_present": mentioned or None,
        "source_url": url,
        "note": "Observed from a single web source; unverified. A researcher must confirm before use.",
    }
    excerpt = text[:600] if text else None
    summary = (title or (teams and f"{teams[0]} v {teams[1]}") or url)
    return Extraction(kind=kind, title=title, summary=summary[:200] if summary else None,
                      confidence=confidence, candidate=candidate, raw_excerpt=excerpt,
                      cricket_relevant=cricket_relevant)
