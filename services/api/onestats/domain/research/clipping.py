"""Parse a newspaper/scorebook scorecard clipping into a *draft* (Phase 10, Stage 10.17).

This turns OCR'd or transcribed scorecard text into structured draft rows so a researcher can review
and correct them before anything is saved. It is deliberately conservative and honest about uncertainty:

  * It is a **pure** function — it reads text and returns data. It never touches the database, never
    creates people, and never asserts a figure it did not actually read. Unknown stays ``None`` (never 0).
  * Every parsed row keeps the ``raw`` source line so the researcher can see exactly what was read.
  * Names are returned as *text only*. Matching a name to an existing player (or deciding to create a
    new one) is a separate, researcher-driven step — this module only extracts the name as written.

The caller (the research API) layers candidate existing-player matches on top of these names; the
researcher confirms every name and figure, and only then are players created and a draft scorecard built.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

# --- dismissal classification -------------------------------------------------------------------
# A parsed batting line is classified into a dismissal *kind* only when the text is unambiguous; the
# descriptive text is always kept verbatim so the researcher can see and correct it. We never guess a
# fielder/bowler identity here — their names are kept as written for the separate matching step.
DISMISSAL_KINDS = (
    "bowled", "caught", "caught_and_bowled", "lbw", "run_out", "stumped",
    "not_out", "retired", "did_not_bat", "hit_wicket", "other",
)

_NOT_OUT_RE = re.compile(r"\bnot\s*out\b", re.IGNORECASE)
_DNB_RE = re.compile(r"\bdid\s*not\s*bat\b|\bdnb\b|\babsent\b", re.IGNORECASE)
_RETIRED_RE = re.compile(r"\bretired\b", re.IGNORECASE)
_RUN_OUT_RE = re.compile(r"\brun\s*out\b", re.IGNORECASE)
_HIT_WICKET_RE = re.compile(r"\bhit\s*wicket\b", re.IGNORECASE)
_CAUGHT_BOWLED_RE = re.compile(r"\bc\s*(?:&|and)\s*b\b", re.IGNORECASE)
_STUMPED_RE = re.compile(r"\bst\b", re.IGNORECASE)
_LBW_RE = re.compile(r"\blbw\b", re.IGNORECASE)
# "c Fielder b Bowler"  /  "c †Keeper b Bowler"  /  "c sub b Bowler"
_CAUGHT_RE = re.compile(r"\bc\b\.?\s+(?P<fielder>.+?)\s+\bb\b\.?\s+(?P<bowler>.+?)\s*$", re.IGNORECASE)
# "b Bowler"  (bowled)   — bowler is the remainder
_BOWLED_RE = re.compile(r"^\s*b\b\.?\s+(?P<bowler>.+?)\s*$", re.IGNORECASE)
# "lbw b Bowler" / "lbw Bowler"
_LBW_BOWLER_RE = re.compile(r"\blbw\b\.?\s+(?:b\b\.?\s+)?(?P<bowler>.+?)\s*$", re.IGNORECASE)
# trailing "b Bowler" anywhere (stumped/caught&bowled/hit-wicket all name a bowler)
_TRAILING_BOWLER_RE = re.compile(r"\bb\b\.?\s+(?P<bowler>[^,]+?)\s*$", re.IGNORECASE)

# Lines that are totals/summaries, not a batter — skipped (but reported) so we never invent a player.
_SUMMARY_RE = re.compile(
    r"^\s*(extras?|total|sundries|byes?|leg\s*byes?|wides?|no[\s-]*balls?|"
    r"fall\s+of\s+wickets?|fow|bowling|did\s+not\s+bat|to\s+bat|innings|"
    r"\d+\s*(?:st|nd|rd|th)\s+innings)\b",
    re.IGNORECASE,
)

# A bowling analysis figure: O-M-R-W, e.g. "10-2-35-4" or "9.2-1-28-3" (overs may be N.B balls).
_BOWLING_FIG_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<overs>\d+(?:\.\d+)?)[\s\-–](?P<maidens>\d+)[\s\-–]"
    r"(?P<runs>\d+)[\s\-–](?P<wickets>\d+)\s*$"
)

# A name is letters, initials with optional dots, apostrophes, hyphens and spaces. Deliberately strict
# so stray OCR punctuation does not become part of a player's name.
_NAME_CLEAN_RE = re.compile(r"[^A-Za-z.'\- ]")


@dataclass
class DraftBatter:
    position: int                       # 1-based reading order within the innings
    name: str                           # the batter's name, exactly as read (cleaned of stray chars)
    runs: int | None = None             # None = unknown (NOT zero)
    balls: int | None = None
    dismissal_kind: str | None = None   # one of DISMISSAL_KINDS, or None when unclear
    dismissal_text: str | None = None   # the descriptive dismissal, verbatim ("c Jones b Brown")
    bowler_name: str | None = None      # text only, for the separate matching step
    fielder_name: str | None = None     # text only (catcher/stumper), for matching
    raw: str = ""                       # the original source line


@dataclass
class DraftBowler:
    position: int
    name: str
    overs_text: str | None = None
    maidens: int | None = None
    runs_conceded: int | None = None
    wickets: int | None = None
    raw: str = ""


@dataclass
class ParsedClipping:
    batters: list[DraftBatter] = field(default_factory=list)
    bowlers: list[DraftBowler] = field(default_factory=list)
    unparsed_lines: list[str] = field(default_factory=list)   # lines we deliberately did not interpret

    def to_dict(self) -> dict[str, Any]:
        return {
            "batters": [asdict(b) for b in self.batters],
            "bowlers": [asdict(b) for b in self.bowlers],
            "unparsed_lines": self.unparsed_lines,
            "disclaimer": (
                "Parsed from text as a draft only. Figures read as unknown are left blank, never zero. "
                "No players are created and nothing is saved until you review and confirm."
            ),
        }


def _clean_name(raw: str) -> str:
    """Trim stray OCR punctuation from a name while keeping initials, apostrophes and hyphens."""
    name = _NAME_CLEAN_RE.sub(" ", raw or "")
    name = re.sub(r"\s+", " ", name).strip(" .-")
    return name


def _trailing_runs(line: str) -> tuple[int | None, int | None, str]:
    """Pull a trailing runs figure (and optional balls in parentheses) off a batting line.

    Returns (runs, balls, remainder). Runs is the last standalone integer on the line; a parenthesised
    number immediately around it is read as balls faced, e.g. "42 (63)" -> runs 42, balls 63. When no
    trailing number is present (e.g. "P Hayter not out" with the score cut off), runs stays None/unknown.
    """
    balls: int | None = None
    s = line.rstrip()
    # "(63)" balls hanging off the end -> capture then strip
    m_balls = re.search(r"\((\d{1,3})\)\s*$", s)
    if m_balls:
        balls = int(m_balls.group(1))
        s = s[: m_balls.start()].rstrip()
    m_runs = re.search(r"(?<![\d.])(\d{1,3})\s*\*?\s*$", s)
    if not m_runs:
        return None, balls, s
    runs = int(m_runs.group(1))
    remainder = s[: m_runs.start()].rstrip()
    return runs, balls, remainder


def _classify(dismissal: str) -> tuple[str | None, str | None, str | None]:
    """Classify a dismissal string -> (kind, bowler_name, fielder_name). Names are text only."""
    d = dismissal.strip()
    if not d:
        return None, None, None
    if _NOT_OUT_RE.search(d):
        return "not_out", None, None
    if _DNB_RE.search(d):
        return "did_not_bat", None, None
    if _RETIRED_RE.search(d):
        return "retired", None, None
    if _RUN_OUT_RE.search(d):
        return "run_out", None, None
    if _CAUGHT_BOWLED_RE.search(d):
        m = _TRAILING_BOWLER_RE.search(d)
        return "caught_and_bowled", _clean_name(m.group("bowler")) if m else None, None
    if _HIT_WICKET_RE.search(d):
        m = _TRAILING_BOWLER_RE.search(d)
        return "hit_wicket", _clean_name(m.group("bowler")) if m else None, None
    if _STUMPED_RE.match(d):  # "st Keeper b Bowler"
        m = re.match(r"st\b\.?\s+(?P<keeper>.+?)\s+b\b\.?\s+(?P<bowler>.+?)\s*$", d, re.IGNORECASE)
        if m:
            return "stumped", _clean_name(m.group("bowler")), _clean_name(m.group("keeper"))
        return "stumped", None, None
    if _LBW_RE.search(d):
        m = _LBW_BOWLER_RE.search(d)
        return "lbw", _clean_name(m.group("bowler")) if m else None, None
    m = _CAUGHT_RE.match(d)
    if m:
        return "caught", _clean_name(m.group("bowler")), _clean_name(m.group("fielder"))
    m = _BOWLED_RE.match(d)
    if m:
        return "bowled", _clean_name(m.group("bowler")), None
    return "other", None, None


# A batting line must start with a plausible name: 1–4 leading tokens of letters/initials.
_LEADS_WITH_NAME_RE = re.compile(r"^\s*[A-Za-z][A-Za-z.'\-]*(?:\s+[A-Za-z][A-Za-z.'\-]*){0,3}\b")
# Where the name ends and the dismissal begins: the first dismissal keyword token.
_DISMISSAL_START_RE = re.compile(
    r"\s+(c\b|b\b|lbw\b|st\b|run\s*out\b|not\s*out\b|retired\b|hit\s*wicket\b|did\s*not\s*bat\b|absent\b)",
    re.IGNORECASE,
)


def _parse_batting_line(line: str, position: int) -> DraftBatter | None:
    runs, balls, remainder = _trailing_runs(line)
    split = _DISMISSAL_START_RE.search(remainder)
    if split:
        name = _clean_name(remainder[: split.start()])
        dismissal_text = remainder[split.start():].strip()
    else:
        # No dismissal keyword: accept as a name-only row only when there is a trailing score to anchor
        # it (otherwise it is prose, not a scorecard row).
        if runs is None:
            return None
        name = _clean_name(remainder)
        dismissal_text = None
    if not name or len(name) < 2 or not re.search(r"[A-Za-z]", name):
        return None
    kind, bowler, fielder = _classify(dismissal_text or "")
    return DraftBatter(
        position=position, name=name, runs=runs, balls=balls, dismissal_kind=kind,
        dismissal_text=dismissal_text, bowler_name=bowler, fielder_name=fielder, raw=line.strip(),
    )


def _parse_bowling_line(line: str, position: int) -> DraftBowler | None:
    m = _BOWLING_FIG_RE.match(line.strip())
    if not m:
        return None
    name = _clean_name(m.group("name"))
    if not name or len(name) < 2:
        return None
    return DraftBowler(
        position=position, name=name, overs_text=m.group("overs"), maidens=int(m.group("maidens")),
        runs_conceded=int(m.group("runs")), wickets=int(m.group("wickets")), raw=line.strip(),
    )


def parse_clipping(text_in: str) -> ParsedClipping:
    """Parse scorecard text into draft batting and bowling rows. Pure; creates nothing.

    Batting rows are detected first (a name + a dismissal and/or trailing score). Lines that match a
    bowling analysis (O-M-R-W) become bowling rows. Totals/summary lines and anything ambiguous are
    returned in ``unparsed_lines`` rather than guessed at.
    """
    result = ParsedClipping()
    bat_pos = 0
    bowl_pos = 0
    for raw_line in (text_in or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _SUMMARY_RE.match(line):
            result.unparsed_lines.append(line)
            continue
        bowler = _parse_bowling_line(line, bowl_pos + 1)
        if bowler is not None:
            bowl_pos += 1
            result.bowlers.append(bowler)
            continue
        if _LEADS_WITH_NAME_RE.match(line):
            batter = _parse_batting_line(line, bat_pos + 1)
            if batter is not None:
                bat_pos += 1
                result.batters.append(batter)
                continue
        result.unparsed_lines.append(line)
    return result
