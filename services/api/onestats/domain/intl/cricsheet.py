"""Cricsheet match parser — ball-by-ball JSON to a structured scorecard (Part E).

Cricsheet (https://cricsheet.org) publishes each match as a JSON document under an open licence: match
metadata plus every delivery. This module turns ONE such document into a normalised, OneStats-shaped
scorecard (per-innings batting, bowling and fall-of-wickets aggregates) WITHOUT touching the database
or the network — the importer (:mod:`onestats.domain.intl.cricsheet_import`) maps the result onto the
match tables.

The input bytes are DATA, never instructions (prompt-injection hardening): we read only the fields we
expect and coerce types defensively. The aggregation is cricket-accurate and era-safe:

  * over length comes from ``info.balls_per_over`` (6 or the historical 8) — never assumed;
  * a bowler is charged with runs off the bat plus wides and no-balls, but NOT byes/leg-byes;
  * a legal ball (for the bowler's over count and the batter's balls faced) excludes wides and no-balls
    — a wide is not even faced by the striker, a no-ball is faced but is not a legal ball;
  * a maiden is an over conceding no bat-runs, wides or no-balls (byes alone still leave it a maiden);
  * only bowler-credited dismissals (bowled, caught, lbw, stumped, caught-and-bowled, hit-wicket) count
    to the bowler — run-outs, retirements, obstruction, etc. do not;
  * declarations, forfeits and Super Overs are carried through; nothing is invented and unknowns stay
    unknown.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

# Cricsheet match_type -> OneStats format. Only the three recognised MEN'S international formats are
# accepted here; anything else (domestic, women's lists, youth) is rejected by the caller's choice of
# dataset and by :func:`parse_match` raising.
_MATCH_TYPE_FORMAT = {"Test": "test", "ODI": "odi", "IT20": "t20i", "T20": "t20i"}

# Dismissal kinds credited to the bowler. Everything else (run out, retired hurt/out, obstructing the
# field, handled the ball, timed out, absent) is not the bowler's wicket.
_BOWLER_WICKET_KINDS = {"bowled", "caught", "lbw", "stumped", "caught and bowled", "hit wicket"}

# Cricsheet extras keys that are charged to the bowler (byes/leg-byes/penalty are not).
_BOWLER_EXTRAS = ("wides", "noballs")


@dataclass
class ParsedBatting:
    name: str
    position: int
    runs: int = 0
    balls_faced: int = 0
    fours: int = 0
    sixes: int = 0
    out: bool = False
    dismissal_kind: str | None = None     # Cricsheet kind, e.g. "caught", "lbw" (None if not out)
    bowler: str | None = None             # crediting bowler name, if any
    fielders: list[str] = field(default_factory=list)


@dataclass
class ParsedBowling:
    name: str
    order: int
    legal_balls: int = 0
    runs_conceded: int = 0
    wickets: int = 0
    maidens: int = 0
    wides: int = 0
    noballs: int = 0


@dataclass
class ParsedFall:
    wicket_number: int
    player_out: str
    team_runs: int                        # team total when the wicket fell


@dataclass
class ParsedInnings:
    batting_team: str
    bowling_team: str
    declared: bool = False
    forfeited: bool = False
    super_over: bool = False
    total_runs: int = 0
    total_wickets: int = 0
    legal_balls: int = 0
    extras: dict[str, int] = field(default_factory=dict)
    batting: list[ParsedBatting] = field(default_factory=list)
    bowling: list[ParsedBowling] = field(default_factory=list)
    fall_of_wickets: list[ParsedFall] = field(default_factory=list)


@dataclass
class ParsedMatch:
    source_ref: str                       # Cricsheet match id (the caller supplies it, e.g. the filename)
    format: str                           # test | odi | t20i
    gender: str
    balls_per_over: int
    dates: list[dt.date]
    teams: list[str]
    players: dict[str, list[str]]
    registry: dict[str, str]              # player name -> Cricsheet person id (stable cross-source id)
    venue: str | None
    city: str | None
    event_name: str | None
    match_number: int | None
    toss: dict[str, Any]
    outcome: dict[str, Any]
    innings: list[ParsedInnings]

    @property
    def start_date(self) -> dt.date | None:
        return self.dates[0] if self.dates else None


def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _date(s: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def parse_match(doc: dict[str, Any], *, source_ref: str) -> ParsedMatch:
    """Parse one Cricsheet match document (already JSON-decoded) into a :class:`ParsedMatch`.

    Raises ``ValueError`` for anything outside the three recognised men's international formats or a
    structurally unusable document, so a bad/unexpected file is refused rather than half-imported.
    """
    if not isinstance(doc, dict):
        raise ValueError("cricsheet_not_an_object")
    info = doc.get("info")
    if not isinstance(info, dict):
        raise ValueError("cricsheet_missing_info")

    match_type = str(info.get("match_type", ""))
    fmt = _MATCH_TYPE_FORMAT.get(match_type)
    if fmt is None:
        raise ValueError(f"cricsheet_unsupported_match_type:{match_type or 'unknown'}")
    gender = str(info.get("gender", "")).lower()
    if gender != "male":
        # this workspace is men's international cricket; a women's/other file is not ours to import
        raise ValueError(f"cricsheet_unsupported_gender:{gender or 'unknown'}")

    balls_per_over = _as_int(info.get("balls_per_over", 6), 6) or 6
    dates = [d for d in (_date(x) for x in info.get("dates", []) or []) if d is not None]
    teams = [str(t) for t in info.get("teams", []) or []]
    players = {str(team): [str(p) for p in plist]
               for team, plist in (info.get("players", {}) or {}).items()}
    registry = {str(name): str(pid)
                for name, pid in ((info.get("registry", {}) or {}).get("people", {}) or {}).items()}
    event = info.get("event", {}) or {}

    innings = [_parse_innings(i, balls_per_over, teams) for i in (doc.get("innings", []) or [])]

    return ParsedMatch(
        source_ref=str(source_ref), format=fmt, gender=gender, balls_per_over=balls_per_over,
        dates=dates, teams=teams, players=players, registry=registry,
        venue=(str(info["venue"]) if info.get("venue") else None),
        city=(str(info["city"]) if info.get("city") else None),
        event_name=(str(event.get("name")) if event.get("name") else None),
        match_number=(_as_int(event["match_number"]) if event.get("match_number") is not None else None),
        toss=(info.get("toss", {}) or {}), outcome=(info.get("outcome", {}) or {}),
        innings=innings,
    )


def _parse_innings(raw: dict[str, Any], balls_per_over: int, teams: list[str]) -> ParsedInnings:
    batting_team = str(raw.get("team", ""))
    bowling_team = next((t for t in teams if t != batting_team), "")
    inns = ParsedInnings(
        batting_team=batting_team, bowling_team=bowling_team,
        declared=bool(raw.get("declared")), forfeited=bool(raw.get("forfeited")),
        super_over=bool(raw.get("super_over")),
    )
    # ordered accumulators keyed by player name, so batting/bowling order is preserved
    bat: dict[str, ParsedBatting] = {}
    bowl: dict[str, ParsedBowling] = {}
    extras_total: dict[str, int] = {}

    def batter(name: str) -> ParsedBatting:
        if name not in bat:
            bat[name] = ParsedBatting(name=name, position=len(bat) + 1)
        return bat[name]

    def bowler(name: str) -> ParsedBowling:
        if name not in bowl:
            bowl[name] = ParsedBowling(name=name, order=len(bowl) + 1)
        return bowl[name]

    for over in raw.get("overs", []) or []:
        deliveries = over.get("deliveries", []) or []
        over_bowler_runs = 0          # bat-runs + wides + no-balls charged to the bowler this over
        over_bowler: str | None = None
        for d in deliveries:
            runs = d.get("runs", {}) or {}
            extras = d.get("extras", {}) or {}
            bat_runs = _as_int(runs.get("batter"))
            striker = str(d.get("batter", ""))
            bowl_name = str(d.get("bowler", ""))
            over_bowler = bowl_name
            is_wide = "wides" in extras
            is_noball = "noballs" in extras

            b = batter(striker)
            b.runs += bat_runs
            if not is_wide:                       # a wide is not faced by the striker
                b.balls_faced += 1
            if bat_runs == 4:
                b.fours += 1
            elif bat_runs == 6:
                b.sixes += 1

            bw = bowler(bowl_name)
            charged = bat_runs + _as_int(extras.get("wides")) + _as_int(extras.get("noballs"))
            bw.runs_conceded += charged
            over_bowler_runs += charged
            bw.wides += _as_int(extras.get("wides"))
            bw.noballs += _as_int(extras.get("noballs"))
            if not is_wide and not is_noball:     # legal delivery
                bw.legal_balls += 1
                inns.legal_balls += 1

            inns.total_runs += _as_int(runs.get("total", bat_runs))
            for key, val in extras.items():
                extras_total[key] = extras_total.get(key, 0) + _as_int(val)

            for w in d.get("wickets", []) or []:
                kind = str(w.get("kind", ""))
                out_name = str(w.get("player_out", striker))
                ob = batter(out_name)
                ob.out = True
                ob.dismissal_kind = kind
                ob.fielders = [str(f.get("name")) for f in (w.get("fielders", []) or []) if f.get("name")]
                if kind in _BOWLER_WICKET_KINDS:
                    ob.bowler = bowl_name
                    bw.wickets += 1
                inns.total_wickets += 1
                inns.fall_of_wickets.append(
                    ParsedFall(wicket_number=inns.total_wickets, player_out=out_name,
                               team_runs=inns.total_runs))
        # maiden: the bowler conceded no bat-runs, wides or no-balls this over (byes alone are fine)
        if over_bowler is not None and over_bowler_runs == 0 and deliveries:
            bowler(over_bowler).maidens += 1

    inns.extras = extras_total
    inns.batting = list(bat.values())
    inns.bowling = list(bowl.values())
    return inns
