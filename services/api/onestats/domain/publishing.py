"""Website publishing (Phase 15, deliverable 29) — hosting-neutral.

Publishing a report or a public player profile creates a ``publication`` with a permanent unguessable
slug and a durable **snapshot** (rendered data + self-contained HTML + checksum + branding). Public access
reads the snapshot only — it never touches the live engine or the admin database, so it works while the
Windows computer is offline and serves the **last successfully published approved snapshot**.

The same snapshot feeds either (a) **static export** — files uploaded to existing website hosting (the RMCC
site's External URL field) — or (b) a future **central OneStats publishing service**. Nothing commits to
either approach. Only approved, publication-eligible data is snapshotted (no DOB/junior/private), so public
exposure is intended. Numbers always come from the one deterministic engine.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime
from html import escape
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.core.config import Settings
from onestats.domain import audit, branding, logos, photos, profiles
from onestats.domain.records import player_profile
from onestats.reports import catalogue

_COLS = ("id, workspace_id, kind, report_id, person_id, title, filters, slug, status, stale, "
         "snapshot, snapshot_html, checksum, snapshot_at, created_by, created_at, updated_at")


def _slug() -> str:
    return secrets.token_urlsafe(12)


def _file_data_uri(path: Any, *, thumb: bool = False) -> str | None:
    """Turn a stored image file into a self-contained ``data:`` URI, so a published page carries its
    images and works offline with no server. ``thumb`` prefers the small PNG thumbnail (kept alongside
    the original) when present. Returns None when the file is missing or unreadable."""
    if path is None:
        return None
    if thumb:
        thumb_path = path.with_name(path.name + ".thumb.png")
        if thumb_path.exists():
            path = thumb_path
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    ext = path.suffix.lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "gif": "gif", "svg": "svg+xml"}.get(ext, "png")
    return f"data:image/{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _logo_data_uri(settings: Settings | None, workspace_id: UUID, logo_ref: str | None,
                   *, thumb: bool = False) -> str | None:
    """A stored club logo/crest as a ``data:`` URI (hero logo uses the original; crests use thumbnails)."""
    if settings is None or not logo_ref:
        return None
    try:
        return _file_data_uri(logos.logo_path(settings, workspace_id, logo_ref), thumb=thumb)
    except ValueError:
        return None


def _public_photo_data_uri(conn: Connection, settings: Settings | None, workspace_id: UUID,
                           person_id: UUID) -> str | None:
    """The player's primary photo as a ``data:`` URI — but ONLY a photo explicitly marked public
    (``public_visible``). A photo that is not cleared for public use is never published."""
    if settings is None:
        return None
    key = conn.execute(
        text("SELECT media_key FROM person_photo WHERE person_id = :p AND public_visible = true "
             "ORDER BY is_primary DESC, created_at LIMIT 1"),
        {"p": person_id},
    ).scalar_one_or_none()
    if not key:
        return None
    try:
        return _file_data_uri(photos.photo_path(settings, workspace_id, key), thumb=True)
    except ValueError:
        return None


def _branding(conn: Connection, workspace_id: UUID) -> dict[str, Any]:
    ws = conn.execute(text("SELECT name FROM workspace WHERE id = :w"), {"w": workspace_id}).mappings().first()
    b = branding.get_branding(conn, workspace_id) or {}
    return {"club": (ws or {}).get("name") or "OneStats",
            "primary": b.get("primary_colour") or "#0b5e3b",
            "secondary": b.get("secondary_colour"), "accent": b.get("accent_colour"),
            "theme": b.get("theme_mode") or "system", "logo_ref": b.get("logo_ref")}


def _filters(workspace_id: UUID, saved: dict[str, Any]) -> dict[str, Any]:
    f: dict[str, Any] = {"workspace_id": workspace_id}
    for k in ("season_id", "grade_id", "competition_id", "team_id", "split", "venue", "format"):
        if saved.get(k):
            f[k] = saved[k]
    return f


def _report_snapshot(conn: Connection, workspace_id: UUID, report_id: str, saved_filters: dict[str, Any],
                     brand: dict[str, Any]) -> dict[str, Any]:
    data = catalogue.report_rows(conn, workspace_id, report_id, _filters(workspace_id, saved_filters))
    entry = catalogue.CAT_BY_ID.get(report_id)
    quals = [n for n in ((entry.qualification if entry else None), (entry.limitations if entry else None)) if n]
    quals.append("Official statistics from approved scorecards only; unknown values are never treated as zero.")
    return {"kind": "report", "report_id": report_id, "report_name": data["title"],
            "columns": data["columns"], "rows": data["rows"], "qualifications": quals, "branding": brand}


def _club_crests(conn: Connection, settings: Settings | None, workspace_id: UUID,
                 clubs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """The clubs a player represented, each with its own crest (embedded) when the organisation has one."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in clubs or []:
        name = c.get("club")
        if not name or name in seen:
            continue
        seen.add(name)
        ref = None
        if c.get("org_id"):
            ref = conn.execute(
                text("SELECT logo_ref FROM organisation WHERE id = :o AND workspace_id = :w"),
                {"o": c["org_id"], "w": workspace_id}).scalar_one_or_none()
        out.append({"club": name, "crest": _logo_data_uri(settings, workspace_id, ref, thumb=True)})
    return out


def _profile_snapshot(conn: Connection, workspace_id: UUID, person_id: UUID, brand: dict[str, Any],
                      filters: dict[str, Any] | None = None, settings: Settings | None = None) -> dict[str, Any]:
    # public career view strips internal / non-public / DOB / junior data (deliverable 12a/29.4a)
    view = profiles.career_view(conn, person_id, public=True) or {}
    org_raw = (filters or {}).get("organisation_id")
    org_id = UUID(str(org_raw)) if org_raw else None
    prof = player_profile.full_profile(conn, workspace_id, person_id, organisation_id=org_id)
    person = view.get("person") or {}
    det = prof.get("detail") or {}
    # Public playing-style/service detail — club-appropriate public info only (no DOB, no contact).
    public_detail = {"batting_style": det.get("batting_style"), "bowling_style": det.get("bowling_style"),
                     "is_wicketkeeper": det.get("is_wicketkeeper"), "biography": det.get("biography"),
                     "numbers": det.get("numbers") or [],
                     "leadership": det.get("leadership") or [], "recognition": det.get("recognition") or []}
    # When a club is chosen, the published figures are that club's ONLY: full_profile scopes career, match
    # span and grand finals by organisation. Season-by-season and all-time records are NOT club-scoped, so
    # they are omitted on a club-scoped profile rather than leak figures from other clubs. Honours and
    # badges stay — they are the player's own recognition, not other clubs' match statistics.
    scope_club = None
    seasons = prof.get("seasons") or []
    records = prof.get("records") or []
    clubs = _club_crests(conn, settings, workspace_id, prof.get("clubs"))
    if org_id is not None:
        scope_club = next((c.get("club") for c in (prof.get("clubs") or [])
                           if str(c.get("org_id")) == str(org_id)), None)
        seasons, records = [], []
        clubs = [c for c in clubs if c["club"] == scope_club]  # don't list other clubs on a club profile
    b = prof.get("badges") or {}
    badges = {"calculated": [{"label": x.get("label"), "state": x.get("state")} for x in (b.get("calculated") or [])],
              "awarded": [{"label": x.get("label")} for x in (b.get("awarded") or [])]}
    quals = [("Public profile — approved statistics only; personal contact details and "
              "dates of birth are never published.")]
    if scope_club:
        quals.insert(0, f"Statistics shown for {scope_club} only — figures from other clubs are not included.")
    brand = {**brand, "logo": _logo_data_uri(settings, workspace_id, brand.get("logo_ref"))}
    photo = _public_photo_data_uri(conn, settings, workspace_id, person_id)
    return {"kind": "player_profile", "person_name": person.get("display_name") or "Player",
            "detail": public_detail, "span": prof.get("span"), "scope_club": scope_club, "photo": photo,
            "career": prof["career"], "seasons": seasons, "records": records, "clubs": clubs,
            "grand_finals": prof.get("grand_finals"), "badges": badges,
            "honours": [{"title": h.get("title"), "category": h.get("award_category") or h.get("honour_type"),
                         "season": h.get("awarded_season")} for h in prof["honours"]],
            "branding": brand, "qualifications": quals}


def _num(v: Any, dp: int = 0) -> str:
    """Format a stat value for display; unknown → em dash (never shown as zero when truly unknown)."""
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{dp}f}"
    return escape(str(v))


def _tiles(pairs: list[tuple[str, str]]) -> str:
    """A responsive grid of stat tiles (label + big value). Values are already formatted/escaped."""
    cells = "".join(f"<div class='tile'><span>{escape(lbl)}</span><b>{val}</b></div>" for lbl, val in pairs)
    return f"<div class='tiles'>{cells}</div>"


def _table(headers: list[tuple[str, str]], rows: list[str]) -> str:
    """A branded, horizontally-scrollable table. ``headers`` is (label, align) where align is 'r' or ''.
    ``rows`` are ready-made ``<tr>…</tr>`` strings."""
    head = "".join(f"<th class='{'r' if a == 'r' else ''}'>{escape(h)}</th>" for h, a in headers)
    return f"<div class='tbl'><table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


_PROFILE_CSS = (
    # Surface tokens — the club's selected theme (light / dark / system) swaps these; the brand colour
    # is used for the hero, tables and accents in every theme.
    ":root{--bg:#eef2f0;--card:#fff;--ink:#1a2420;--muted:#64726b;--line:#e3e9e6;--line2:#eef2f0;"
    "--zebra:#f6f9f7;--tabbg:#fff;--tabink:#51605a;--shadow:rgba(0,0,0,.06)}"
    ".theme-dark{--bg:#0f1512;--card:#18211d;--ink:#e9efec;--muted:#9aa8a1;--line:#273129;"
    "--line2:#1f2822;--zebra:#1d2620;--tabbg:#141b17;--tabink:#9aa8a1;--shadow:rgba(0,0,0,.45)}"
    "@media(prefers-color-scheme:dark){.theme-system{--bg:#0f1512;--card:#18211d;--ink:#e9efec;"
    "--muted:#9aa8a1;--line:#273129;--line2:#1f2822;--zebra:#1d2620;--tabbg:#141b17;--tabink:#9aa8a1;"
    "--shadow:rgba(0,0,0,.45)}}"
    "*{box-sizing:border-box}html{scroll-behavior:smooth}"
    "body{font-family:'Segoe UI',system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif;margin:0;"
    "color:var(--ink);background:var(--bg);-webkit-font-smoothing:antialiased}"
    ".hero{background:var(--brand);background:linear-gradient(135deg,var(--brand),"
    "color-mix(in srgb,var(--brand) 70%,#000));color:#fff}"
    ".hero-in{max-width:1040px;margin:0 auto;padding:26px 20px 22px;display:flex;align-items:center;"
    "gap:22px;flex-wrap:wrap}"
    ".avatar{width:92px;height:92px;border-radius:50%;overflow:hidden;background:#fff;flex:0 0 auto;"
    "display:flex;align-items:center;justify-content:center;box-shadow:0 2px 12px rgba(0,0,0,.3)}"
    ".avatar img{width:100%;height:100%;object-fit:cover}"
    ".avatar.crest img{object-fit:contain;padding:8px}"
    ".avatar.mono{background:rgba(255,255,255,.16);color:#fff;font-weight:800;font-size:33px;"
    "border:2px solid rgba(255,255,255,.4)}"
    ".id{flex:1 1 240px;min-width:200px}"
    ".id .club{text-transform:uppercase;letter-spacing:.09em;font-size:12px;opacity:.9;font-weight:600;"
    "display:flex;align-items:center}"
    ".club-crest{width:20px;height:20px;object-fit:contain;margin-right:7px;border-radius:4px;background:#fff;"
    "padding:1px}"
    ".id h1{margin:.08em 0 .22em;font-size:30px;line-height:1.08;font-weight:800;letter-spacing:-.01em}"
    ".chips{display:flex;gap:7px;flex-wrap:wrap;margin:.1em 0}"
    ".chip{background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.3);border-radius:999px;"
    "padding:3px 11px;font-size:12.5px;font-weight:500}"
    ".hero .meta{font-size:12.5px;opacity:.9;margin-top:.5em}"
    ".keys{display:flex;gap:10px;flex-wrap:wrap}"
    ".key{background:rgba(255,255,255,.13);border:1px solid rgba(255,255,255,.24);border-radius:12px;"
    "padding:10px 15px;text-align:center;min-width:74px}"
    ".key span{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.05em;opacity:.85}"
    ".key b{font-size:23px;font-weight:800;line-height:1.15;font-variant-numeric:tabular-nums}"
    ".tabs{position:sticky;top:0;z-index:5;background:var(--tabbg);border-bottom:1px solid var(--line);"
    "display:flex;gap:2px;overflow-x:auto;padding:0 10px;box-shadow:0 1px 5px var(--shadow)}"
    ".tabs .tab{appearance:none;background:none;border:0;border-bottom:3px solid transparent;"
    "color:var(--tabink);font:inherit;font-size:14px;font-weight:600;padding:13px 14px;cursor:pointer;"
    "white-space:nowrap}"
    ".tabs .tab:hover{color:var(--brand)}"
    ".tabs .tab.on{color:var(--brand);border-bottom-color:var(--brand)}"
    "main{max-width:1040px;margin:0 auto;padding:20px}"
    ".panel{display:none}.panel.on{display:block;animation:fade .24s ease}"
    "@keyframes fade{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}"
    "h3.sub{color:var(--brand);font-size:12.5px;text-transform:uppercase;letter-spacing:.05em;"
    "margin:22px 0 9px;font-weight:700}"
    ".tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(112px,1fr));gap:12px;margin:4px 0}"
    ".tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;"
    "box-shadow:0 1px 2px var(--shadow)}"
    ".tile span{display:block;font-size:11px;color:var(--muted);text-transform:uppercase;"
    "letter-spacing:.04em;margin-bottom:4px}"
    ".tile b{font-size:23px;font-weight:800;color:var(--ink);font-variant-numeric:tabular-nums}"
    ".tbl{overflow-x:auto;border:1px solid var(--line);border-radius:12px;margin:8px 0;background:var(--card)}"
    "table{border-collapse:collapse;width:100%;font-size:13.5px}"
    "th{background:var(--brand);color:#fff;padding:9px 12px;text-align:left;font-weight:600;white-space:nowrap}"
    "td{padding:8px 12px;border-top:1px solid var(--line2);color:var(--ink);"
    "font-variant-numeric:tabular-nums;white-space:nowrap}"
    "th.r,td.r{text-align:right}tbody tr:nth-child(even) td{background:var(--zebra)}"
    ".badges{display:flex;gap:8px;flex-wrap:wrap;margin:2px 0 6px}"
    ".badge{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:5px 13px;"
    "font-size:12.5px;color:var(--ink);font-weight:500}"
    ".badge.hon{background:var(--brand);color:#fff;border-color:var(--brand)}"
    ".clubs{display:flex;gap:12px;flex-wrap:wrap;margin:4px 0}"
    ".clubrow{display:flex;align-items:center;gap:9px;background:var(--card);border:1px solid var(--line);"
    "border-radius:12px;padding:7px 15px 7px 7px}"
    ".clubrow img{width:34px;height:34px;object-fit:contain;border-radius:6px;background:#f2f5f3}"
    ".clubrow .mono{width:34px;height:34px;border-radius:6px;background:var(--brand);color:#fff;display:flex;"
    "align-items:center;justify-content:center;font-weight:800;font-size:15px}"
    ".clubrow b{font-size:14px;font-weight:600;color:var(--ink)}"
    ".list{margin:6px 0;padding-left:1.1em;font-size:14px;color:var(--ink)}.list li{margin:.3em 0}"
    ".muted{color:var(--muted);font-size:12.5px}"
    ".scope{background:color-mix(in srgb,var(--brand) 12%,var(--card));"
    "border:1px solid color-mix(in srgb,var(--brand) 32%,var(--card));border-radius:10px;"
    "padding:10px 14px;font-size:13px;color:var(--ink);margin:2px 0 14px}"
    ".bio{font-size:14px;line-height:1.6;color:var(--ink);white-space:pre-wrap;max-width:720px}"
    "footer{max-width:1040px;margin:0 auto;padding:16px 20px 36px;color:var(--muted);font-size:11.5px}"
    "@media(max-width:560px){.id h1{font-size:24px}.hero-in{gap:14px}.key b{font-size:19px}}"
)

_PROFILE_JS = (
    "(function(){var t=[].slice.call(document.querySelectorAll('.tab'));"
    "var p=[].slice.call(document.querySelectorAll('.panel'));"
    "function show(id){t.forEach(function(b){b.classList.toggle('on',b.dataset.target===id)});"
    "p.forEach(function(s){s.classList.toggle('on',s.id===id)})}"
    "t.forEach(function(b){b.addEventListener('click',function(){show(b.dataset.target);"
    "if(history.replaceState)history.replaceState(null,'','#'+b.dataset.target)})});"
    "var h=location.hash.replace('#','');"
    "show(h&&document.getElementById(h)?h:(t[0]&&t[0].dataset.target));})();"
)


def _profile_tabs(snap: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Build the (id, label, html) for each profile tab that has data to show."""
    c = snap.get("career") or {}
    det = snap.get("detail") or {}
    bat, bowl = c.get("batting") or {}, c.get("bowling") or {}
    field, capt = c.get("fielding") or {}, c.get("captaincy") or {}
    gf = snap.get("grand_finals") or {}
    tabs: list[tuple[str, str, str]] = []

    # ---- Overview ----
    ov: list[str] = []
    if snap.get("scope_club"):
        ov.append(f"<div class='scope'><b>Statistics for {escape(str(snap['scope_club']))} only.</b> "
                  "Figures from any other club are not included.</div>")
    bdg = snap.get("badges") or {}
    # Honour-grade recognitions (Life Member, honorary member, …) and recorded honours are the most
    # prestigious, so they lead as filled badges; calculated statistical milestones follow.
    chips = [f"<span class='badge hon'>{escape(str(r.get('label') or ''))}</span>"
             for r in (det.get("recognition") or [])]
    chips += [f"<span class='badge hon'>{escape(str(x.get('label') or ''))}</span>" for x in (bdg.get("awarded") or [])]
    chips += [f"<span class='badge'>{escape(str(x.get('label') or ''))}"
              + (" ≥" if "known_minimum" in str(x.get("state") or "") else "") + "</span>"
              for x in (bdg.get("calculated") or [])]
    if chips:
        ov.append("<div class='badges'>" + "".join(chips) + "</div>")
    ov.append(_tiles([
        ("Matches", _num(c.get("matches", 0))), ("Runs", _num(bat.get("runs", 0))),
        ("Bat avg", _num(bat.get("average"), 2)), ("Highest", _hs(bat)),
        ("Wickets", _num(bowl.get("wickets", 0))), ("Bowl avg", _num(bowl.get("average"), 2)),
        ("Best bowling", _bb(bowl)), ("Catches", _num(field.get("catches", 0))),
        ("Stumpings", _num(field.get("stumpings", 0))), ("Run-outs", _num(field.get("run_outs", 0)))]))
    clubs = snap.get("clubs") or []
    if clubs:
        rows = []
        for cl in clubs:
            nm = escape(str(cl.get("club") or ""))
            crest = cl.get("crest")
            mark = (f"<img src='{crest}' alt=''>" if crest
                    else f"<span class='mono'>{escape((cl.get('club') or '?')[:1].upper())}</span>")
            rows.append(f"<div class='clubrow'>{mark}<b>{nm}</b></div>")
        ov.append("<h3 class='sub'>Clubs</h3><div class='clubs'>" + "".join(rows) + "</div>")
    if det.get("biography"):
        ov.append(f"<h3 class='sub'>Biography</h3><p class='bio'>{escape(str(det['biography']))}</p>")
    tabs.append(("overview", "Overview", "".join(ov)))

    # ---- Batting ----
    if int(bat.get("innings", 0) or 0) > 0:
        bt = _tiles([
            ("Innings", _num(bat.get("innings"))), ("Not outs", _num(bat.get("not_outs"))),
            ("Runs", _num(bat.get("runs"))), ("Highest", _hs(bat)), ("Average", _num(bat.get("average"), 2)),
            ("Strike rate", _num(bat.get("strike_rate"), 1)), ("Fifties", _num(bat.get("fifties"))),
            ("Hundreds", _num(bat.get("hundreds"))), ("Ducks", _num(bat.get("ducks"))),
            ("Fours", _num(bat.get("fours"))), ("Sixes", _num(bat.get("sixes")))])
        tbl = _table(
            [("M", ""), ("Inns", "r"), ("NO", "r"), ("Runs", "r"), ("HS", "r"), ("Avg", "r"),
             ("50", "r"), ("100", "r"), ("SR", "r")],
            ["<tr><td>" + _num(bat.get("matches")) + "</td>"
             + "".join(f"<td class='r'>{v}</td>" for v in (
                 _num(bat.get("innings")), _num(bat.get("not_outs")), _num(bat.get("runs")), _hs(bat),
                 _num(bat.get("average"), 2), _num(bat.get("fifties")), _num(bat.get("hundreds")),
                 _num(bat.get("strike_rate"), 1))) + "</tr>"])
        tabs.append(("batting", "Batting", bt + "<h3 class='sub'>Career</h3>" + tbl))

    # ---- Bowling ----
    if int(bowl.get("innings", 0) or 0) > 0:
        bl = _tiles([
            ("Innings", _num(bowl.get("innings"))), ("Overs", _num(bowl.get("overs"), 1)),
            ("Maidens", _num(bowl.get("maidens"))), ("Runs", _num(bowl.get("runs"))),
            ("Wickets", _num(bowl.get("wickets"))), ("Average", _num(bowl.get("average"), 2)),
            ("Economy", _num(bowl.get("economy"), 2)), ("Strike rate", _num(bowl.get("strike_rate"), 1)),
            ("Best bowling", _bb(bowl)), ("5 wkts", _num(bowl.get("five_wkt_innings"))),
            ("Hat-tricks", _num(bowl.get("hat_tricks"))), ("Best (match)", _num(bowl.get("best_match_wickets")))])
        tbl = _table(
            [("M", ""), ("Overs", "r"), ("Mdns", "r"), ("Runs", "r"), ("Wkts", "r"), ("Avg", "r"),
             ("Econ", "r"), ("SR", "r"), ("BB", "r"), ("5w", "r")],
            ["<tr><td>" + _num(bowl.get("matches")) + "</td>"
             + "".join(f"<td class='r'>{v}</td>" for v in (
                 _num(bowl.get("overs"), 1), _num(bowl.get("maidens")), _num(bowl.get("runs")),
                 _num(bowl.get("wickets")), _num(bowl.get("average"), 2), _num(bowl.get("economy"), 2),
                 _num(bowl.get("strike_rate"), 1), _bb(bowl), _num(bowl.get("five_wkt_innings")))) + "</tr>"])
        tabs.append(("bowling", "Bowling", bl + "<h3 class='sub'>Career</h3>" + tbl))

    # ---- Fielding & keeping ----
    if any(int(field.get(k, 0) or 0) > 0 for k in
           ("catches", "stumpings", "run_outs", "run_out_assists", "keeper_dismissals")):
        fl = _tiles([
            ("Catches", _num(field.get("catches"))), ("Outfield", _num(field.get("field_catches"))),
            ("Keeper catches", _num(field.get("keeper_catches"))), ("Stumpings", _num(field.get("stumpings"))),
            ("Run-outs", _num(field.get("run_outs"))), ("Run-out assists", _num(field.get("run_out_assists"))),
            ("Keeper dismissals", _num(field.get("keeper_dismissals")))])
        tabs.append(("fielding", "Fielding & WK", fl))

    # ---- Captaincy ----
    if int(capt.get("captained", 0) or 0) > 0:
        cp = int(capt.get("captained", 0) or 0)
        won = int(capt.get("wins", 0) or 0)
        win_pct = f"{(won * 100 / cp):.0f}%" if cp else "—"
        tabs.append(("captaincy", "Captaincy", _tiles([
            ("Captained", _num(capt.get("captained"))), ("Won", _num(capt.get("wins"))),
            ("Lost", _num(capt.get("losses"))), ("Drawn", _num(capt.get("draws"))),
            ("Tied", _num(capt.get("ties"))), ("Win %", win_pct),
            ("GF captained", _num(capt.get("gf_captained"))), ("GF won", _num(capt.get("gf_wins")))])))

    # ---- Seasons ----
    seasons = snap.get("seasons") or []
    if seasons:
        rows = ["<tr><td>" + escape(str(s.get("label") or "")) + "</td>"
                + "".join(f"<td class='r'>{v}</td>" for v in (
                    _num(s.get("matches")), _num(s.get("runs")), _num(s.get("batting_average"), 2),
                    _num(s.get("wickets")), _num(s.get("bowling_average"), 2), _num(s.get("catches")))) + "</tr>"
                for s in seasons]
        tabs.append(("seasons", "Seasons", _table(
            [("Season", ""), ("M", "r"), ("Runs", "r"), ("Bat avg", "r"), ("Wkts", "r"),
             ("Bowl avg", "r"), ("Ct", "r")], rows)))

    # ---- Grand Finals ----
    if int(gf.get("appearances", 0) or 0) > 0:
        gfb, gfw, gff = gf.get("batting") or {}, gf.get("bowling") or {}, gf.get("fielding") or {}
        tabs.append(("grandfinals", "Grand Finals", _tiles([
            ("Appearances", _num(gf.get("appearances"))), ("Premierships", _num(gf.get("premierships"))),
            ("GF runs", _num(gfb.get("runs"))), ("GF bat avg", _num(gfb.get("average"), 2)),
            ("GF wickets", _num(gfw.get("wickets"))), ("GF bowl avg", _num(gfw.get("average"), 2)),
            ("GF catches", _num(gff.get("catches")))])))

    # ---- Honours & records ----
    hon: list[str] = []
    records = snap.get("records") or []
    if records:
        items = "".join(
            f"<li>{escape(str(r.get('title') or ''))}"
            + (f" — <b>{_num(r.get('value'))}</b>" if r.get("value") is not None else "")
            + (" <span class='muted'>(tied)</span>" if r.get("tied") else "") + "</li>"
            for r in records)
        hon.append(f"<h3 class='sub'>Records held</h3><ul class='list'>{items}</ul>")
    service: list[str] = []
    for r in (det.get("leadership") or []) + (det.get("recognition") or []):
        seasons_txt = ", ".join(escape(str(x)) for x in (r.get("seasons") or []))
        service.append(f"<li>{escape(str(r.get('label') or ''))}"
                       + (f" <span class='muted'>({seasons_txt})</span>" if seasons_txt else "") + "</li>")
    for h in (snap.get("honours") or []):
        extra = " · ".join(escape(str(x)) for x in (h.get("category"), h.get("season")) if x)
        service.append(f"<li>{escape(str(h.get('title') or ''))}"
                       + (f" <span class='muted'>({extra})</span>" if extra else "") + "</li>")
    if service:
        hon.append(f"<h3 class='sub'>Service &amp; honours</h3><ul class='list'>{''.join(service)}</ul>")
    if hon:
        tabs.append(("honours", "Honours & Records", "".join(hon)))

    return tabs


def _hs(bat: dict[str, Any]) -> str:
    """Highest score with a trailing * when it was not out (never fabricated when unknown)."""
    hs = bat.get("highest_score")
    if hs is None:
        return "—"
    return _num(hs) + ("*" if bat.get("highest_not_out") else "")


def _bb(bowl: dict[str, Any]) -> str:
    bb = bowl.get("best_bowling") or {}
    if bb.get("wickets") is None:
        return "—"
    return f"{_num(bb.get('wickets'))}-{_num(bb.get('runs'))}"


def _render_profile_page(snap: dict[str, Any], title: str, public_base: str, slug: str) -> str:
    """A professional, self-contained, tab-through public player profile (CricketStatz-style): a branded
    hero with the club crest and headline numbers, then clickable tabs for batting, bowling, fielding,
    captaincy, seasons, grand finals and honours. All CSS/JS and images are inlined, so it works offline
    from the snapshot and never touches the database. No DOB/contact/private data is ever included."""
    brand = snap.get("branding") or {}
    primary = escape(str(brand.get("primary") or "#0b5e3b"))
    accent = escape(str(brand.get("accent") or brand.get("secondary") or brand.get("primary") or "#0b5e3b"))
    club = escape(str(brand.get("club") or "OneStats"))
    logo = brand.get("logo")
    det = snap.get("detail") or {}
    c = snap.get("career") or {}
    bat, bowl, field = c.get("batting") or {}, c.get("bowling") or {}, c.get("fielding") or {}
    span = snap.get("span") or {}
    name = escape(str(snap.get("person_name") or title or "Player"))

    # hero style chips
    chips = []
    for label, key in (("Bats", "batting_style"), ("Bowls", "bowling_style")):
        if det.get(key):
            chips.append(f"<span class='chip'>{label} {escape(str(det[key]))}</span>")
    if det.get("is_wicketkeeper"):
        chips.append("<span class='chip'>Wicketkeeper</span>")
    if det.get("numbers"):
        chips.append("<span class='chip'>No. " + escape(", ".join(str(n) for n in det["numbers"])) + "</span>")
    chips_html = f"<div class='chips'>{''.join(chips)}</div>" if chips else ""

    def _edge(e: dict[str, Any] | None) -> str | None:
        if not e or not e.get("date"):
            return None
        opp = e.get("opposition")
        return escape(str(e["date"])) + (f" v {escape(str(opp))}" if opp else "")
    first, last = _edge(span.get("first")), _edge(span.get("last"))
    meta_bits = []
    if first:
        meta_bits.append(f"Debut {first}")
    if last:
        meta_bits.append(f"Most recent {last}")
    meta_html = f"<div class='meta'>{' · '.join(meta_bits)}</div>" if meta_bits else ""

    key_cells = "".join(
        f"<div class='key'><span>{escape(lbl)}</span><b>{val}</b></div>" for lbl, val in (
            ("Matches", _num(c.get("matches", 0))), ("Runs", _num(bat.get("runs", 0))),
            ("Wickets", _num(bowl.get("wickets", 0))), ("Catches", _num(field.get("catches", 0)))))

    # Avatar: the player's own (public) photo first, then the club crest, then an initials monogram.
    photo = snap.get("photo")
    raw_name = str(snap.get("person_name") or title or "Player")
    initials = escape("".join(w[0] for w in raw_name.split()[:2]).upper() or "?")
    if photo:
        avatar_html = f"<div class='avatar'><img src='{photo}' alt='{name}'></div>"
    elif logo:
        avatar_html = f"<div class='avatar crest'><img src='{logo}' alt='{club} logo'></div>"
    else:
        avatar_html = f"<div class='avatar mono'>{initials}</div>"
    # When the photo is the avatar, still show the club crest as a small mark beside the club name.
    club_mark = f"<img class='club-crest' src='{logo}' alt=''>" if (photo and logo) else ""

    theme = str(brand.get("theme") or "system")
    theme_class = "theme-" + (theme if theme in ("light", "dark") else "system")

    tabs = _profile_tabs(snap)
    tabbar = "".join(
        f"<button class='tab' data-target='t_{tid}'>{escape(lbl)}</button>" for tid, lbl, _ in tabs)
    panels = "".join(
        f"<section id='t_{tid}' class='panel'>{html}</section>" for tid, _, html in tabs)
    notes = "".join(f"<p class='muted'>{escape(q)}</p>" for q in snap.get("qualifications", []))
    gen = datetime.now(UTC).strftime("%d %b %Y")
    foot_link = (" · " + escape(public_base) + "/p/" + escape(slug)) if public_base else ""

    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{name} — {club}</title>"
        f"<style>:root{{--brand:{primary};--accent:{accent}}}</style>"
        f"<style>{_PROFILE_CSS}</style></head><body class='{theme_class}'>"
        f"<header class='hero'><div class='hero-in'>{avatar_html}"
        f"<div class='id'><div class='club'>{club_mark}{club}</div><h1>{name}</h1>{chips_html}{meta_html}</div>"
        f"<div class='keys'>{key_cells}</div></div></header>"
        f"<nav class='tabs' role='tablist'>{tabbar}</nav>"
        f"<main>{panels}{('<div>' + notes + '</div>') if notes else ''}</main>"
        f"<footer>Published by OneStats · {gen}{foot_link} · Approved statistics only — "
        "unknown values are never shown as zero.</footer>"
        f"<script>{_PROFILE_JS}</script></body></html>")


def _render_html(snap: dict[str, Any], title: str, public_base: str, slug: str) -> str:
    # Player profiles get the rich, tab-through page; reports keep the clean single-table page.
    if snap.get("kind") == "player_profile":
        return _render_profile_page(snap, title, public_base, slug)
    brand = snap.get("branding") or {}
    primary = escape(str(brand.get("primary") or "#0b5e3b"))
    club = escape(str(brand.get("club") or "OneStats"))
    gen = datetime.now(UTC).strftime("%d %b %Y")
    body = []
    if snap["kind"] == "report":
        cols, rows = snap["columns"], snap["rows"]
        head = "".join(f"<th style='text-align:{'right' if c['align'] == 'right' else 'left'}'>{escape(c['label'])}</th>" for c in cols)
        trs = []
        for r in rows:
            tds = []
            for c in cols:
                v = r.get(c["key"])
                s = "—" if v is None else (f"{v:.{c['decimals']}f}" if c["decimals"] is not None and isinstance(v, (int, float)) else ("Yes" if v is True else "No" if v is False else escape(str(v))))
                tds.append(f"<td style='text-align:{'right' if c['align'] == 'right' else 'left'}'>{s}</td>")
            trs.append("<tr>" + "".join(tds) + "</tr>")
        body.append(f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(trs)}</tbody></table>")
        if not rows:
            body.append("<p class='muted'>No published data for this report yet.</p>")
    for q in snap.get("qualifications", []):
        body.append(f"<p class='muted'>{escape(q)}</p>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} — {club}</title>
<style>
:root{{--brand:{primary}}}
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;color:#17201c;background:#fff}}
header{{border-bottom:3px solid var(--brand);padding:12px 20px}}
header b{{color:var(--brand)}}
main{{padding:16px 20px;max-width:1000px;margin:0 auto}}
h1{{color:var(--brand);font-size:20px;margin:.2em 0}} h2{{color:var(--brand);margin:.2em 0}}
h3{{color:var(--brand);font-size:15px;margin:1.1em 0 .4em;border-bottom:1px solid #e5eae7;padding-bottom:3px}}
.style{{font-size:14px;color:#2c3a33;margin:.2em 0 .4em}}
.bio{{font-size:14px;line-height:1.5;color:#2c3a33;white-space:pre-wrap}}
ul{{font-size:14px;margin:.3em 0;padding-left:1.2em}} li{{margin:.15em 0}}
td:not(:first-child),th:not(:first-child){{text-align:right}}
table{{border-collapse:collapse;width:100%;font-size:14px;margin:.2em 0}}
th{{background:var(--brand);color:#fff;padding:6px 8px}} td{{padding:5px 8px;border-bottom:1px solid #e5eae7}}
tr:nth-child(even) td{{background:#f3f6f4}}
.cards{{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}}
.card{{border:1px solid #e5eae7;border-radius:8px;padding:8px 14px}} .card span{{display:block;font-size:12px;color:#5b665f}} .card b{{font-size:20px}}
.badges{{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}}
.badge{{background:#f3f6f4;border:1px solid #e5eae7;border-radius:999px;padding:3px 10px;font-size:12px;color:#2c3a33}}
.badge-honour{{background:var(--brand);color:#fff;border-color:var(--brand)}}
.scope{{font-size:13px;color:#2c3a33;margin:.3em 0}}
.muted{{color:#5b665f;font-size:12px}} footer{{color:#8a938d;font-size:11px;padding:10px 20px;border-top:1px solid #e5eae7}}
</style></head><body>
<header><b>{club}</b></header>
<main><h1>{escape(title)}</h1>{''.join(body)}</main>
<footer>Published by OneStats · {gen}{(' · ' + escape(public_base) + '/r/' + escape(slug)) if public_base else ''}</footer>
</body></html>"""


def _snapshot(conn: Connection, settings: Settings, workspace_id: UUID, row: dict[str, Any]) -> dict[str, Any]:
    brand = _branding(conn, workspace_id)
    if row["kind"] == "report":
        snap = _report_snapshot(conn, workspace_id, row["report_id"], row.get("filters") or {}, brand)
    else:
        snap = _profile_snapshot(conn, workspace_id, row["person_id"], brand, row.get("filters"), settings)
    snap["title"] = row["title"]
    snap["generated_at"] = datetime.now(UTC).isoformat()
    html = _render_html(snap, row["title"], settings.public_base_url or "", row["slug"])
    checksum = hashlib.sha256(json.dumps(snap, sort_keys=True, default=str).encode()).hexdigest()
    return {"snapshot": snap, "html": html, "checksum": checksum}


def _row(conn: Connection, workspace_id: UUID, pub_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text(f"SELECT {_COLS} FROM publication WHERE id = :id AND workspace_id = :w"),
                     {"id": pub_id, "w": workspace_id}).mappings().first()
    return dict(r) if r else None


def create_publication(conn: Connection, settings: Settings, workspace_id: UUID, actor: str, *, kind: str,
                       title: str, report_id: str | None = None, person_id: UUID | None = None,
                       filters: dict[str, Any] | None = None) -> dict[str, Any]:
    if kind not in ("report", "player_profile"):
        raise ValueError("invalid_kind")
    if kind == "report" and (not report_id or report_id not in catalogue.CAT_BY_ID):
        raise ValueError("unknown_report")
    if kind == "player_profile" and not person_id:
        raise ValueError("person_required")
    if kind == "player_profile" and (filters or {}).get("organisation_id"):
        ok = conn.execute(text("SELECT 1 FROM organisation WHERE id = CAST(:o AS uuid) AND workspace_id = :w"),
                          {"o": str(filters["organisation_id"]), "w": workspace_id}).first()
        if ok is None:
            raise ValueError("unknown_organisation")
    slug = _slug()
    pub_id = conn.execute(
        text("INSERT INTO publication(workspace_id, kind, report_id, person_id, title, filters, slug, status, created_by) "
             "VALUES (:w,:k,:rid,:pid,:t,CAST(:f AS jsonb),:s,'published',:a) RETURNING id"),
        {"w": workspace_id, "k": kind, "rid": report_id, "pid": person_id, "t": title,
         "f": json.dumps(filters or {}), "s": slug, "a": actor},
    ).scalar_one()
    _store_snapshot(conn, settings, workspace_id, pub_id)
    audit.write_audit(conn, workspace_id, actor, "publication.create", entity="publication", entity_id=str(pub_id))
    return _row(conn, workspace_id, pub_id)


def _store_snapshot(conn: Connection, settings: Settings, workspace_id: UUID, pub_id: UUID) -> None:
    row = _row(conn, workspace_id, pub_id)
    if row is None:
        raise ValueError("publication_not_found")
    s = _snapshot(conn, settings, workspace_id, row)
    conn.execute(
        text("UPDATE publication SET snapshot = CAST(:snap AS jsonb), snapshot_html = :html, checksum = :ck, "
             "snapshot_at = now(), stale = false, updated_at = now() WHERE id = :id AND workspace_id = :w"),
        {"snap": json.dumps(s["snapshot"], default=str), "html": s["html"], "ck": s["checksum"],
         "id": pub_id, "w": workspace_id},
    )


def set_status(conn: Connection, workspace_id: UUID, actor: str, pub_id: UUID, status: str) -> dict[str, Any]:
    if status not in ("published", "unpublished", "revoked"):
        raise ValueError("invalid_status")
    if _row(conn, workspace_id, pub_id) is None:
        raise ValueError("publication_not_found")
    conn.execute(text("UPDATE publication SET status = :s, updated_at = now() WHERE id = :id AND workspace_id = :w"),
                 {"s": status, "id": pub_id, "w": workspace_id})
    audit.write_audit(conn, workspace_id, actor, f"publication.{status}", entity="publication", entity_id=str(pub_id))
    return _row(conn, workspace_id, pub_id)


def republish(conn: Connection, settings: Settings, workspace_id: UUID, actor: str, pub_id: UUID) -> dict[str, Any]:
    if _row(conn, workspace_id, pub_id) is None:
        raise ValueError("publication_not_found")
    _store_snapshot(conn, settings, workspace_id, pub_id)
    conn.execute(text("UPDATE publication SET status = 'published' WHERE id = :id AND workspace_id = :w"),
                 {"id": pub_id, "w": workspace_id})
    audit.write_audit(conn, workspace_id, actor, "publication.republish", entity="publication", entity_id=str(pub_id))
    return _row(conn, workspace_id, pub_id)


def refresh_workspace(conn: Connection, settings: Settings, workspace_id: UUID, actor: str) -> dict[str, Any]:
    """Regenerate the snapshot of every published publication (automatic update after approved-stat
    changes). Public serving keeps using the last snapshot until this succeeds, so it never goes dark."""
    ids = conn.execute(text("SELECT id FROM publication WHERE workspace_id = :w AND status = 'published'"),
                       {"w": workspace_id}).scalars().all()
    for pid in ids:
        _store_snapshot(conn, settings, workspace_id, pid)
    if ids:
        audit.write_audit(conn, workspace_id, actor, "publication.refresh", entity="workspace",
                          entity_id=str(workspace_id), after={"refreshed": len(ids)})
    return {"refreshed": len(ids)}


def list_publications(conn: Connection, workspace_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT id, kind, report_id, person_id, title, filters, slug, status, stale, checksum, snapshot_at "
             "FROM publication WHERE workspace_id = :w ORDER BY created_at DESC"), {"w": workspace_id}).mappings().all()
    return [{k: (str(v) if isinstance(v, UUID) else v) for k, v in dict(r).items()} for r in rows]


def get_public_base_url(conn: Connection, workspace_id: UUID) -> str | None:
    """The public web address this workspace's published site is hosted at (e.g. a GitHub Pages URL),
    or None when nothing is hosted yet (the download-and-upload default)."""
    return conn.execute(
        text("SELECT public_base_url FROM workspace WHERE id = :w"), {"w": workspace_id}
    ).scalar_one_or_none()


def set_public_base_url(conn: Connection, workspace_id: UUID, actor: str, url: str | None) -> str | None:
    """Store the public hosting address for this workspace. An empty value clears it (back to 'not hosted
    yet'). A non-empty value must be an absolute http(s) URL; the trailing slash is normalised away so the
    stored value joins cleanly with ``/r/<slug>.html`` paths. Display/address only — never changes what is
    served, which stays the cached, approved-only snapshots."""
    cleaned = (url or "").strip().rstrip("/")
    if cleaned and not cleaned.startswith(("http://", "https://")):
        raise ValueError("invalid_base_url")
    value = cleaned or None
    before = get_public_base_url(conn, workspace_id)
    conn.execute(text("UPDATE workspace SET public_base_url = :u WHERE id = :w"),
                 {"u": value, "w": workspace_id})
    audit.write_audit(conn, workspace_id, actor, "publication.set_base_url", entity="workspace",
                      entity_id=str(workspace_id), before={"public_base_url": before},
                      after={"public_base_url": value})
    return value


def get_public(conn: Connection, slug: str) -> dict[str, Any] | None:
    """Resolve a published snapshot by slug with NO workspace context (public, offline-capable). Returns
    None for unknown / unpublished / revoked slugs (so unpublish/revoke make the URL stop resolving)."""
    r = conn.execute(
        text("SELECT title, kind, snapshot, snapshot_html, checksum, snapshot_at FROM publication "
             "WHERE slug = :s AND status = 'published'"), {"s": slug}).mappings().first()
    return dict(r) if r else None


def public_portal(conn: Connection, workspace_id: UUID) -> dict[str, Any]:
    """The public mobile records portal index for a club (Phase 16) — the published reports and profiles,
    read from the publication edge with NO workspace context. Approved, published, non-private data only;
    independent of server uptime (it uses the stored snapshots). Club name/colour come from the snapshots."""
    rows = conn.execute(
        text("SELECT title, kind, slug, snapshot->'branding'->>'club' AS club, "
             "snapshot->'branding'->>'primary' AS primary FROM publication "
             "WHERE workspace_id = :w AND status = 'published' ORDER BY kind DESC, title"),
        {"w": workspace_id}).mappings().all()
    club = next((r["club"] for r in rows if r["club"]), "OneStats")
    primary = next((r["primary"] for r in rows if r["primary"]), "#0b5e3b")
    items = [{"title": r["title"], "kind": r["kind"], "slug": r["slug"],
              "path": f"/api/v1/public/{'p' if r['kind'] == 'player_profile' else 'r'}/{r['slug']}"}
             for r in rows]
    return {"club": club, "primary": primary, "items": items, "workspace_id": str(workspace_id)}


def member_portal(conn: Connection, workspace_id: UUID) -> dict[str, Any]:
    """The authenticated member portal index for a club — the **public** published items PLUS the
    non-public catalogue (unpublished drafts members may see), each flagged with its public status. Runs
    WITH workspace context, so RLS scopes it to the member's workspace; revoked items are excluded. This is
    the permission-scoped read-only surface for additional non-public data (Phase 16 follow-up)."""
    rows = conn.execute(
        text("SELECT title, kind, slug, status, stale, snapshot_at FROM publication "
             "WHERE workspace_id = :w AND status IN ('published','unpublished') "
             "ORDER BY kind DESC, title"),
        {"w": workspace_id}).mappings().all()
    branding = conn.execute(
        text("SELECT primary_colour FROM branding WHERE workspace_id = :w"), {"w": workspace_id}).mappings().first()
    ws = conn.execute(text("SELECT name FROM workspace WHERE id = :w"), {"w": workspace_id}).mappings().first()
    items = [{"title": r["title"], "kind": r["kind"], "slug": r["slug"], "status": r["status"],
              "public": r["status"] == "published", "stale": bool(r["stale"]),
              "path": (f"/api/v1/public/{'p' if r['kind'] == 'player_profile' else 'r'}/{r['slug']}"
                       if r["status"] == "published" else None),
              "snapshot_at": r["snapshot_at"].isoformat() if r["snapshot_at"] else None}
             for r in rows]
    return {"club": (ws or {}).get("name") or "OneStats",
            "primary": (branding or {}).get("primary_colour") or "#0b5e3b",
            "items": items, "workspace_id": str(workspace_id),
            "public_count": sum(1 for i in items if i["public"]),
            "member_only_count": sum(1 for i in items if not i["public"])}


def render_portal_html(portal: dict[str, Any]) -> str:
    """A mobile-first, branded, read-only portal index page (no DB; works offline from snapshots)."""
    primary = escape(str(portal.get("primary") or "#0b5e3b"))
    club = escape(str(portal.get("club") or "OneStats"))
    reports = [i for i in portal["items"] if i["kind"] == "report"]
    players = [i for i in portal["items"] if i["kind"] == "player_profile"]

    def _section(name: str, items: list[dict[str, Any]]) -> str:
        if not items:
            return ""
        links = "".join(
            f"<li data-name='{escape(i['title'].lower())}'><a href='{escape(i['path'])}'>{escape(i['title'])}</a></li>"
            for i in items)
        return f"<h2>{escape(name)}</h2><ul class='list'>{links}</ul>"

    body = _section("Players", players) + _section("Reports", reports)
    if not portal["items"]:
        body = "<p class='muted'>No published records yet.</p>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{club} — Records</title>
<style>
:root{{--brand:{primary}}}
*{{box-sizing:border-box}}
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;color:#17201c;background:#f7f9f8}}
header{{background:var(--brand);color:#fff;padding:16px;position:sticky;top:0}}
header h1{{margin:0;font-size:18px}}
main{{max-width:680px;margin:0 auto;padding:16px}}
.search{{width:100%;padding:12px;font-size:16px;border:1px solid #d8dcd9;border-radius:10px;margin-bottom:12px}}
h2{{color:var(--brand);font-size:15px;margin:18px 0 6px}}
.list{{list-style:none;padding:0;margin:0}}
.list li{{background:#fff;border:1px solid #e5eae7;border-radius:10px;margin-bottom:8px}}
.list a{{display:block;padding:14px 16px;color:#17201c;text-decoration:none;font-size:16px}}
.list a:active{{background:#eef3f0}}
.muted{{color:#5b665f}} footer{{color:#8a938d;font-size:11px;text-align:center;padding:16px}}
</style></head><body>
<header><h1>{club} — Records</h1></header>
<main>
<input class="search" type="search" placeholder="Search players and reports…" aria-label="Search"
 oninput="var q=this.value.toLowerCase();document.querySelectorAll('.list li').forEach(function(li){{li.style.display=li.dataset.name.indexOf(q)>-1?'':'none'}})">
{body}
</main>
<footer>Read-only records portal · published by OneStats</footer>
</body></html>"""


def static_export(conn: Connection, workspace_id: UUID, pub_id: UUID) -> dict[str, str]:
    """The self-contained files for uploading to existing website hosting: a JSON feed + an HTML page."""
    row = _row(conn, workspace_id, pub_id)
    if row is None or row.get("snapshot") is None:
        raise ValueError("publication_not_found")
    snap = row["snapshot"] if isinstance(row["snapshot"], dict) else json.loads(row["snapshot"])
    return {f"{row['slug']}.json": json.dumps({"title": row["title"], **snap}, indent=2, default=str),
            f"{row['slug']}.html": row["snapshot_html"] or ""}


_SITE_README = """OneStats — public records site
================================

These files are your club's published reports and player profiles, already rendered and branded. They
are static: they need no server and never touch your database. Upload the WHOLE folder (keep the r/ and
p/ sub-folders and the .nojekyll file) to any static web host.

GitHub Pages
------------
1. Create a repository (e.g. "<club>-stats") on GitHub.
2. Upload every file in this folder, keeping the folder structure.
3. In the repository: Settings -> Pages -> Deploy from a branch -> main -> / (root) -> Save.
4. After a minute your site is live at  https://<your-username>.github.io/<repository>/
5. Back in OneStats -> Website Publishing, paste that address into "Public site address" and Save.
   The copyable public URL for each report then appears and can be linked from your club website.

When your statistics change, click "Refresh all" in OneStats, export this folder again, and re-upload it.
Only approved, public, non-private data is ever included.
"""


def site_export(conn: Connection, workspace_id: UUID) -> dict[str, str]:
    """The ENTIRE published site for a workspace as a set of static files laid out for a static host
    (e.g. GitHub Pages): a branded index page that links to every published report and profile, each
    report/profile's self-contained HTML page and JSON feed under ``r/`` and ``p/``, a ``.nojekyll`` marker
    (so hosts serve the files as-is) and a README with upload steps. Published items only; approved,
    non-private data only (the snapshots already enforce this)."""
    ws = conn.execute(text("SELECT name FROM workspace WHERE id = :w"), {"w": workspace_id}).mappings().first()
    brand = branding.get_branding(conn, workspace_id) or {}
    rows = conn.execute(
        text("SELECT kind, slug, title, snapshot, snapshot_html FROM publication "
             "WHERE workspace_id = :w AND status = 'published' ORDER BY kind, title"),
        {"w": workspace_id},
    ).mappings().all()

    files: dict[str, str] = {".nojekyll": "", "README.txt": _SITE_README}
    items: list[dict[str, Any]] = []
    for r in rows:
        folder = "p" if r["kind"] == "player_profile" else "r"
        snap = r["snapshot"] if isinstance(r["snapshot"], dict) else json.loads(r["snapshot"])
        files[f"{folder}/{r['slug']}.html"] = r["snapshot_html"] or ""
        files[f"{folder}/{r['slug']}.json"] = json.dumps({"title": r["title"], **snap}, indent=2, default=str)
        items.append({"title": r["title"], "kind": r["kind"], "path": f"{folder}/{r['slug']}.html"})

    portal = {
        "club": (ws or {}).get("name") or "OneStats",
        "primary": brand.get("primary_colour") or "#0b5e3b",
        "items": items,
    }
    files["index.html"] = render_portal_html(portal)
    return files
