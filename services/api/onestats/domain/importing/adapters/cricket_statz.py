"""CricketStatz source adapter (Phase 8, Stage 8.2).

The first adapter: it maps a CricketStatz JSON export into the Canonical Cricket Data Model. It is the
single source of truth for CricketStatz field knowledge — it reuses the **verified** HOWOUT legend and
result/matchtype/toss encodings from :mod:`onestats.domain.imports` (never re-deriving them), so the
existing importer and this adapter cannot drift. The proven staging/promotion path consumes the CCDM
from Stage 8.3 onward; until then this adapter is the canonical, fully-tested CS→CCDM mapping.

Invariants preserved: a CricketStatz ``0`` person/entity reference means *none* (→ ``None``, never a
real id); the raw ``Howout`` code is always kept (``dismissal_source_code``) while the mapped type is
left ``None`` when the code is not in the verified legend; the toss winner is a home/away code
(1 = home, 2 = away, 0 = not recorded) and the bat/bowl decision is absent (left unknown); nothing is
inferred and unknown is never coerced to zero.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from onestats.domain.importing.adapter import SourceAdapter, register_adapter
from onestats.domain.importing.model import (
    CanonicalBattingEntry,
    CanonicalBowlingEntry,
    CanonicalClub,
    CanonicalDataset,
    CanonicalFow,
    CanonicalGrade,
    CanonicalInnings,
    CanonicalMatch,
    CanonicalPerson,
    CanonicalTeam,
    CanonicalVenue,
    SourceProvenance,
    clean_ref,
)
from onestats.domain.imports import MATCHTYPE_LABELS, RESULT_LABELS, map_howout


def _ref0(value: Any) -> str | None:
    """A CricketStatz person/entity reference where 0/blank means none/unknown (never a real id)."""
    return None if value in (None, 0, "0", "") else str(value)


def _num(value: Any) -> int | None:
    """An integer, or None for blank/unknown. Unknown is NEVER coerced to 0; a real 0 stays 0."""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _name(first: Any, last: Any) -> str | None:
    s = f"{(first or '').strip()} {(last or '').strip()}".strip()
    return s or None


def _toss_winner(code: Any) -> str | None:
    """1 = home side, 2 = away side, 0/other = not recorded (→ None). Same home/away convention as
    Result; never inferred from batting order or result."""
    if code in (1, "1"):
        return "home"
    if code in (2, "2"):
        return "away"
    return None


class CricketStatzAdapter(SourceAdapter):
    format_id = "cricket_statz"
    display_name = "CricketStatz export (JSON)"
    capabilities = frozenset({"matches", "scorecards", "people", "toss", "captains", "keepers"})

    # ---- detect ----------------------------------------------------------------------------------
    def detect(self, sample: bytes | str, filename: str | None = None) -> float:
        text = sample.decode("utf-8-sig", errors="ignore") if isinstance(sample, bytes) else sample
        head = text[:4000].lower()
        if "\"matchid\"" not in head and "matchid" not in head:
            # a CricketStatz export always carries MatchID; without it this is not our format
            return 0.0
        score = 0.4
        for marker in ("\"players\"", "\"teams\"", "\"matches\"", "howout", "playerid", "battingteam"):
            if marker in head:
                score += 0.12
        return min(score, 0.98)

    # ---- parse -----------------------------------------------------------------------------------
    def parse(self, content: bytes | str, *, filename: str | None = None) -> dict[str, Any]:
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")
        data = json.loads(content)
        if not isinstance(data, dict):
            # a malformed source (not our object shape) is a user-facing import error, not a bug
            raise ValueError("cricket_statz: expected a JSON object at the top level")  # noqa: TRY004
        return data

    # ---- normalize -------------------------------------------------------------------------------
    def normalize(self, raw: dict[str, Any], *, mapping: dict[str, Any] | None = None) -> CanonicalDataset:
        ds = CanonicalDataset(provenance=SourceProvenance(source_system=self.format_id))

        ds.clubs = [CanonicalClub(source_ref=str(c["ClubID"]), name=c.get("Name"))
                    for c in raw.get("clubs") or [] if c.get("ClubID") is not None]
        ds.teams = [CanonicalTeam(source_ref=str(t["TeamID"]), name=t.get("Name"),
                                  club_ref=clean_ref(t.get("ClubID")), source_display_name=t.get("Name"))
                    for t in raw.get("teams") or [] if t.get("TeamID") is not None]
        ds.venues = [CanonicalVenue(source_ref=str(v["GroundID"]), name=v.get("Name"))
                     for v in raw.get("venues") or [] if v.get("GroundID") is not None]
        ds.grades = [CanonicalGrade(source_ref=str(g["GradeID"]), name=g.get("Name"))
                     for g in raw.get("divisions") or [] if g.get("GradeID") is not None]

        people_block = raw.get("players") or []
        # people may also arrive under a nested {"players": [...]} (the controlled-import "people" arg)
        if isinstance(raw.get("people"), dict):
            people_block = raw["people"].get("players") or people_block
        ds.people = [CanonicalPerson(
            source_ref=str(p["PlayerID"]),
            display_name=_name(p.get("Firstname"), p.get("Lastname")),
            first_name=p.get("Firstname"), last_name=p.get("Lastname"),
            dob=_date(p.get("DOB")), dob_precision="exact" if p.get("DOB") else "unknown",
            club_ref=_ref0(p.get("MyClub")),
        ) for p in people_block if p.get("PlayerID") is not None]

        # index the scorecard blocks by match -> innings id
        inns_by_match = self._index(raw.get("innings"))
        bat_by_match = self._index(raw.get("batting"))
        bowl_by_match = self._index(raw.get("bowling"))

        for m in raw.get("matches") or []:
            if m.get("MatchID") is None:
                continue
            ds.matches.append(self._match(m, inns_by_match, bat_by_match, bowl_by_match))
        return ds

    # ---- helpers ---------------------------------------------------------------------------------
    @staticmethod
    def _index(blocks: Any) -> dict[int, dict[int, dict[str, Any]]]:
        """{MatchID: {InningsID: innings_block}} for an innings/batting/bowling section."""
        out: dict[int, dict[int, dict[str, Any]]] = {}
        for b in blocks or []:
            mid = b.get("MatchID")
            if mid is None:
                continue
            per = out.setdefault(mid, {})
            for inn in b.get("cricket_Innings") or []:
                iid = inn.get("InningsID")
                if iid is not None:
                    per[iid] = inn
        return out

    def _match(self, m: dict[str, Any], inns_by_match, bat_by_match, bowl_by_match) -> CanonicalMatch:
        result = m.get("Result")
        result_known = result in RESULT_LABELS
        cm = CanonicalMatch(
            source_ref=str(m["MatchID"]),
            match_date=_date(m.get("DatePlayed")),
            date_precision="exact" if m.get("DatePlayed") else "unknown",
            home_team_ref=clean_ref(m.get("HomeTeam")),
            away_team_ref=clean_ref(m.get("AwayTeam")),
            grade_ref=clean_ref(m.get("Grade")),
            venue_ref=clean_ref(m.get("Ground")),
            round=m.get("round"),
            match_format=MATCHTYPE_LABELS.get(m.get("matchtype")),
            result_code=None if result is None else str(result),
            result_type=RESULT_LABELS.get(result) if result_known else None,
            result_status="known" if result_known else "unresolved",
            home_captain_ref=_person(m, "homecaptain1"),
            home_keeper_ref=_person(m, "homekeeper1"),
            home_keeper2_ref=_person(m, "homekeeper2"),
            away_captain_ref=_person(m, "awaycaptain1"),
            away_keeper_ref=_person(m, "awaykeeper1"),
            away_keeper2_ref=_person(m, "awaykeeper2"),
            toss_won_by=_toss_winner(m.get("tosswonby")),
        )
        mid = m["MatchID"]
        inns_map = inns_by_match.get(mid, {})
        bat_map = bat_by_match.get(mid, {})
        bowl_map = bowl_by_match.get(mid, {})
        for iid in sorted(set(inns_map) | set(bat_map) | set(bowl_map),
                          key=lambda x: (inns_map.get(x, {}).get("InnsNumber") or 0, x)):
            cm.innings.append(self._innings(iid, inns_map.get(iid), bat_map.get(iid), bowl_map.get(iid)))
        return cm

    def _innings(self, iid, inn, bat, bowl) -> CanonicalInnings:
        inn = inn or {}
        ci = CanonicalInnings(
            source_ref=str(iid),
            number=_num(inn.get("InnsNumber")),
            batting_team_ref=clean_ref(inn.get("battingteam")),
            bowling_team_ref=clean_ref(inn.get("bowlingteam")),
            byes=_num(inn.get("Byes")), legbyes=_num(inn.get("Legbyes")),
            wides=_num(inn.get("Wides")), noballs=_num(inn.get("Noballs")),
        )
        for b in (bat or {}).get("cricket_batting") or []:
            ci.batting.append(CanonicalBattingEntry(
                batting_position=_num(b.get("Batpos")),
                person_ref=_ref0(b.get("BatsmanID")),
                dismissal_type=map_howout(b.get("Howout")),
                dismissal_source_code=None if b.get("Howout") is None else str(b.get("Howout")),
                bowler_ref=_ref0(b.get("Bowler")),
                fielder_ref=_ref0(b.get("Fielder")),
                runs=_num(b.get("Score")), balls_faced=_num(b.get("Balls")),
                fours=_num(b.get("fours")), sixes=_num(b.get("sixes")), minutes=_num(b.get("mins")),
                fow_score=_num(b.get("FOW")), fow_position=_num(b.get("FOWPos")),
                fow_bat_ref=_ref0(b.get("FOWBatID")), fow_overs=_float(b.get("FOWOvers")),
            ))
        for bw in (bowl or {}).get("cricket_bowling") or []:
            ci.bowling.append(CanonicalBowlingEntry(
                person_ref=_ref0(bw.get("bowlerID")),
                overs=_float(bw.get("Overs")), maidens=_num(bw.get("Maidens")),
                runs_conceded=_num(bw.get("RunsA")), wickets=_num(bw.get("Wickets")),
                wides=_num(bw.get("wides")), noballs=_num(bw.get("noballs")),
            ))
        # fall of wickets, from the batting rows that record one (same source as the existing importer)
        for b in (bat or {}).get("cricket_batting") or []:
            pos = _num(b.get("FOWPos"))
            if pos:
                ci.fall_of_wickets.append(CanonicalFow(
                    wicket_number=pos, team_score=_num(b.get("FOW")),
                    dismissed_ref=_ref0(b.get("FOWBatID")) or _ref0(b.get("BatsmanID")),
                    overs=_float(b.get("FOWOvers")),
                ))
        return ci


def _person(match_row: dict[str, Any], key: str) -> str | None:
    return _ref0(match_row.get(key))


# register the adapter in the process-wide registry
register_adapter(CricketStatzAdapter())
