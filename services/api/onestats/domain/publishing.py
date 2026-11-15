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
import re
import secrets
from datetime import UTC, datetime
from html import escape
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.core.config import Settings
from onestats.domain import audit, branding, logos, photos, profiles
from onestats.domain.records import player_analysis, player_profile
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
                     brand: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    data = catalogue.report_rows(conn, workspace_id, report_id, _filters(workspace_id, saved_filters))
    entry = catalogue.CAT_BY_ID.get(report_id)
    quals = [n for n in ((entry.qualification if entry else None), (entry.limitations if entry else None)) if n]
    quals.append("Official statistics from approved scorecards only; unknown values are never treated as zero.")
    brand = {**brand, "logo": _logo_data_uri(settings, workspace_id, brand.get("logo_ref"))}
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


def _collapse_badge_ladders(calculated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """For the published badge row, keep only the highest milestone reached in each ladder — e.g. just
    '5000 career runs', not every 100 / 500 / 1000 / 2500 below it. Count badges ('2× Century',
    '4× Five-Wicket Innings', '1× Hat-trick') are distinct achievements rather than a ladder, so each is
    kept. Order: one top badge per ladder category (first-seen order), then the count badges."""
    best: dict[str, tuple[int, dict[str, Any]]] = {}
    order: list[str] = []
    others: list[dict[str, Any]] = []
    for badge in calculated:
        label = str(badge.get("label") or "")
        if "×" in label:                       # a count badge — not a ladder, keep every one
            others.append(badge)
            continue
        cat = str(badge.get("category") or label)
        m = re.match(r"\s*(\d+)", label)
        n = int(m.group(1)) if m else 0
        if cat not in best:
            order.append(cat)
            best[cat] = (n, badge)
        elif n > best[cat][0]:
            best[cat] = (n, badge)
    return [best[c][1] for c in order] + others


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
    # When a club is chosen, every published figure is that club's ONLY: full_profile scopes career, match
    # span, grand finals AND the season-by-season line by organisation, and the deep analysis / match list
    # below are scoped too — so a club profile carries the same reports as the whole-career one, for that
    # club alone, never leaking another club's figures. All-time records held are workspace-wide (not a
    # single-club figure), so they are the one report omitted on a club profile. Honours and badges stay —
    # they are the player's own recognition, not other clubs' match statistics.
    scope_club = None
    seasons = prof.get("seasons") or []        # full_profile scopes these by club when org_id is set
    records = prof.get("records") or []
    clubs = _club_crests(conn, settings, workspace_id, prof.get("clubs"))
    if org_id is not None:
        scope_club = next((c.get("club") for c in (prof.get("clubs") or [])
                           if str(c.get("org_id")) == str(org_id)), None)
        records = []                           # all-time records held are workspace-wide, not club-scoped
        clubs = [c for c in clubs if c["club"] == scope_club]  # don't list other clubs on a club profile
    b = prof.get("badges") or {}
    collapsed = _collapse_badge_ladders(b.get("calculated") or [])
    badges = {"calculated": [{"label": x.get("label"), "state": x.get("state")} for x in collapsed],
              "awarded": [{"label": x.get("label")} for x in (b.get("awarded") or [])]}
    quals = [("Public profile — approved statistics only; personal contact details and "
              "dates of birth are never published.")]
    if scope_club:
        quals.insert(0, f"Statistics shown for {scope_club} only — figures from other clubs are not included.")
    brand = {**brand, "logo": _logo_data_uri(settings, workspace_id, brand.get("logo_ref"))}
    photo = _public_photo_data_uri(conn, settings, workspace_id, person_id)
    # Deep analysis (best innings/spells, partnerships, splits by opposition/ground/grade/format, how-out)
    # and the match-by-match list are scoped to the chosen club when one is selected (org_id), so a
    # club-scoped profile shows the same reports as the whole-career one — restricted to that club.
    analysis = player_analysis.player_analysis(conn, workspace_id, person_id, organisation_id=org_id)
    matches = player_profile.match_history(conn, workspace_id, person_id, organisation_id=org_id)
    return {"kind": "player_profile", "person_name": person.get("display_name") or "Player",
            "detail": public_detail, "span": prof.get("span"), "scope_club": scope_club, "photo": photo,
            "analysis": analysis, "matches": matches,
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


def _date(s: Any) -> str:
    """Format an ISO date (YYYY-MM-DD) as '17 Feb 2018'; pass other strings through, unknown → em dash."""
    if not s:
        return "—"
    try:
        d = datetime.fromisoformat(str(s)[:10]).date()
    except ValueError:
        return escape(str(s))
    return d.strftime("%d %b %Y").lstrip("0")


def _tiles(pairs: list[tuple[str, str]]) -> str:
    """A responsive grid of stat tiles (label + big value). Values are already formatted/escaped."""
    cells = "".join(f"<div class='tile'><span>{escape(lbl)}</span><b>{val}</b></div>" for lbl, val in pairs)
    return f"<div class='tiles'>{cells}</div>"


def _table(headers: list[tuple[str, str]], rows: list[str]) -> str:
    """A branded, horizontally-scrollable table. ``headers`` is (label, align) where align is 'r' or ''.
    ``rows`` are ready-made ``<tr>…</tr>`` strings."""
    head = "".join(f"<th class='{'r' if a == 'r' else ''}'>{escape(h)}</th>" for h, a in headers)
    return f"<div class='tbl'><table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


def _chart_scores(innings: list[dict[str, Any]]) -> str:
    """Scores innings-by-innings as thin columns (oldest left), a single brand hue, with dashed 50/100
    reference lines and a per-bar native tooltip. Self-contained SVG; scales to container width."""
    pts = [r for r in innings if r.get("runs") is not None]
    if len(pts) < 2:
        return ""
    w, h, ml, mr, mt, mb = 760, 220, 26, 10, 14, 22
    pw, ph = w - ml - mr, h - mt - mb
    n = len(pts)
    maxv = max(100, max(int(r["runs"]) for r in pts))
    step = pw / n
    bw = max(1.0, step * 0.82)

    def y_of(v: float) -> float:
        return mt + ph - (v / maxv) * ph

    parts = [(f"<svg class='chart' viewBox='0 0 {w} {h}' role='img' preserveAspectRatio='xMidYMid meet' "
              "aria-label='Scores innings by innings'>")]
    parts.append(f"<line class='grid' x1='{ml}' y1='{mt + ph:.1f}' x2='{w - mr}' y2='{mt + ph:.1f}'/>")
    for ref in (50, 100):
        if ref <= maxv:
            yy = y_of(ref)
            parts.append(f"<line class='ref' x1='{ml}' y1='{yy:.1f}' x2='{w - mr}' y2='{yy:.1f}'/>")
            parts.append(f"<text x='{ml - 4}' y='{yy + 3:.1f}' text-anchor='end'>{ref}</text>")
    for i, r in enumerate(pts):
        v = int(r["runs"])
        x = ml + i * step + (step - bw) / 2
        yy = y_of(v)
        cls = "bar no" if r.get("not_out") else "bar"
        star = "*" if r.get("not_out") else ""
        parts.append(f"<rect class='{cls}' x='{x:.1f}' y='{yy:.1f}' width='{bw:.1f}' height='{mt + ph - yy:.1f}' "
                     f"rx='1'><title>{escape(str(r.get('date') or ''))}: {v}{star}</title></rect>")
    parts.append(f"<text x='{ml}' y='{h - 6}' text-anchor='start'>Oldest</text>")
    parts.append(f"<text x='{w - mr}' y='{h - 6}' text-anchor='end'>Most recent</text>")
    parts.append("</svg>")
    return "".join(parts)


def _chart_distribution(freq: list[dict[str, Any]]) -> str:
    """Score distribution: a count of innings in each score band, as a single-hue column chart with the
    count labelled above each bar. Self-contained SVG."""
    if not freq or not any(int(b.get("count") or 0) for b in freq):
        return ""
    w, h, ml, mr, mt, mb = 760, 190, 12, 12, 20, 26
    pw, ph = w - ml - mr, h - mt - mb
    n = len(freq)
    maxc = max((int(b.get("count") or 0) for b in freq), default=0) or 1
    step = pw / n
    bw = step * 0.58
    parts = [(f"<svg class='chart' viewBox='0 0 {w} {h}' role='img' preserveAspectRatio='xMidYMid meet' "
              "aria-label='Score distribution'>")]
    parts.append(f"<line class='grid' x1='{ml}' y1='{mt + ph}' x2='{w - mr}' y2='{mt + ph}'/>")
    for i, b in enumerate(freq):
        c = int(b.get("count") or 0)
        cx = ml + (i + 0.5) * step
        bh = (c / maxc) * ph
        y = mt + ph - bh
        rng = escape(str(b.get("range") or ""))
        parts.append(f"<rect class='bar' x='{cx - bw / 2:.1f}' y='{y:.1f}' width='{bw:.1f}' height='{bh:.1f}' "
                     f"rx='3'><title>{rng}: {c}</title></rect>")
        if c:
            parts.append(f"<text class='val' x='{cx:.1f}' y='{y - 4:.1f}' text-anchor='middle'>{c}</text>")
        parts.append(f"<text x='{cx:.1f}' y='{h - 8}' text-anchor='middle'>{rng}</text>")
    parts.append("</svg>")
    return "".join(parts)


def _chart_wickets(innings: list[dict[str, Any]]) -> str:
    """Wickets innings-by-innings as thin columns (oldest left), a single brand hue, with a dashed
    five-wicket reference line and a per-bar native tooltip showing the figures. Self-contained SVG."""
    pts = [r for r in innings if r.get("wickets") is not None]
    if len(pts) < 2:
        return ""
    w, h, ml, mr, mt, mb = 760, 200, 20, 10, 14, 22
    pw, ph = w - ml - mr, h - mt - mb
    n = len(pts)
    maxv = max(5, max(int(r["wickets"]) for r in pts))
    step = pw / n
    bw = max(1.0, step * 0.82)

    def y_of(v: float) -> float:
        return mt + ph - (v / maxv) * ph

    parts = [(f"<svg class='chart' viewBox='0 0 {w} {h}' role='img' preserveAspectRatio='xMidYMid meet' "
              "aria-label='Wickets innings by innings'>")]
    parts.append(f"<line class='grid' x1='{ml}' y1='{mt + ph:.1f}' x2='{w - mr}' y2='{mt + ph:.1f}'/>")
    if maxv >= 5:
        yy = y_of(5)
        parts.append(f"<line class='ref' x1='{ml}' y1='{yy:.1f}' x2='{w - mr}' y2='{yy:.1f}'/>")
        parts.append(f"<text x='{ml - 4}' y='{yy + 3:.1f}' text-anchor='end'>5</text>")
    for i, r in enumerate(pts):
        v = int(r["wickets"])
        x = ml + i * step + (step - bw) / 2
        yy = y_of(v)
        runs = r.get("runs")
        fig = f"{v}-{runs}" if runs is not None else str(v)
        parts.append(f"<rect class='bar' x='{x:.1f}' y='{yy:.1f}' width='{bw:.1f}' height='{mt + ph - yy:.1f}' "
                     f"rx='1'><title>{escape(str(r.get('date') or ''))}: {escape(fig)}</title></rect>")
    parts.append(f"<text x='{ml}' y='{h - 6}' text-anchor='start'>Oldest</text>")
    parts.append(f"<text x='{w - mr}' y='{h - 6}' text-anchor='end'>Most recent</text>")
    parts.append("</svg>")
    return "".join(parts)


def _chart_by_season(seasons: list[dict[str, Any]], field: str, aria: str) -> str:
    """A column per season (chronological) for one measure — runs or wickets. Single brand hue, the peak
    season directly labelled, sparse season ticks, per-bar tooltips. Self-contained SVG."""
    rows = [s for s in sorted(seasons, key=lambda s: str(s.get("label") or "")) if s.get(field) is not None]
    if len(rows) < 2 or not any(int(s.get(field) or 0) for s in rows):
        return ""
    w, h, ml, mr, mt, mb = 760, 170, 14, 10, 18, 28
    pw, ph = w - ml - mr, h - mt - mb
    n = len(rows)
    maxv = max(int(s.get(field) or 0) for s in rows) or 1
    peak = max(range(n), key=lambda j: int(rows[j].get(field) or 0))
    step = pw / n
    bw = step * 0.66
    tick = max(1, round(n / 8))
    parts = [(f"<svg class='chart' viewBox='0 0 {w} {h}' role='img' preserveAspectRatio='xMidYMid meet' "
              f"aria-label='{escape(aria)}'>")]
    parts.append(f"<line class='grid' x1='{ml}' y1='{mt + ph}' x2='{w - mr}' y2='{mt + ph}'/>")
    for i, s in enumerate(rows):
        v = int(s.get(field) or 0)
        cx = ml + (i + 0.5) * step
        bh = (v / maxv) * ph
        y = mt + ph - bh
        lbl = escape(str(s.get("label") or ""))
        parts.append(f"<rect class='bar' x='{cx - bw / 2:.1f}' y='{y:.1f}' width='{bw:.1f}' height='{bh:.1f}' "
                     f"rx='2'><title>{lbl}: {v}</title></rect>")
        if i == peak:
            parts.append(f"<text class='val' x='{cx:.1f}' y='{y - 4:.1f}' text-anchor='middle'>{v}</text>")
        if i % tick == 0 or i == n - 1:
            parts.append(f"<text x='{cx:.1f}' y='{h - 9}' text-anchor='middle'>{lbl}</text>")
    parts.append("</svg>")
    return "".join(parts)


_PROFILE_CSS = (
    # Surface tokens — the club's selected theme (light / dark / system) swaps these; the brand colour
    # is used for the hero, tables and accents in every theme.
    ":root{--bg:#eef2f0;--card:#fff;--ink:#1a2420;--muted:#64726b;--line:#e3e9e6;--line2:#eef2f0;"
    "--zebra:#f6f9f7;--tabbg:#fff;--tabink:#51605a;--shadow:rgba(0,0,0,.06);"
    "--chart:var(--brand);--chart-soft:color-mix(in srgb,var(--brand) 42%,#fff);--grid:#dde4e0}"
    ".theme-dark{--bg:#0f1512;--card:#18211d;--ink:#e9efec;--muted:#9aa8a1;--line:#273129;"
    "--line2:#1f2822;--zebra:#1d2620;--tabbg:#141b17;--tabink:#9aa8a1;--shadow:rgba(0,0,0,.45);"
    "--chart:color-mix(in srgb,var(--brand) 60%,#fff);--chart-soft:color-mix(in srgb,var(--brand) 32%,#fff);--grid:#2c372f}"
    "@media(prefers-color-scheme:dark){.theme-system{--bg:#0f1512;--card:#18211d;--ink:#e9efec;"
    "--muted:#9aa8a1;--line:#273129;--line2:#1f2822;--zebra:#1d2620;--tabbg:#141b17;--tabink:#9aa8a1;"
    "--shadow:rgba(0,0,0,.45);--chart:color-mix(in srgb,var(--brand) 60%,#fff);"
    "--chart-soft:color-mix(in srgb,var(--brand) 32%,#fff);--grid:#2c372f}}"
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
    ".honours{display:flex;gap:7px;flex-wrap:wrap;margin:.5em 0 .1em}"
    ".hon-badge{background:linear-gradient(135deg,#f7dc82,#e6b43f);color:#3a2c04;border-radius:999px;"
    "padding:3px 12px;font-size:12.5px;font-weight:700;letter-spacing:.01em;"
    "box-shadow:0 1px 4px rgba(0,0,0,.28);border:1px solid rgba(255,255,255,.35)}"
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
    ".chart{width:100%;max-width:760px;height:auto;display:block;margin:8px 0 4px}"
    ".chart .bar{fill:var(--chart)}.chart .bar.no{fill:var(--chart-soft)}"
    ".chart .grid{stroke:var(--line);stroke-width:1}"
    ".chart .ref{stroke:var(--muted);stroke-width:1;stroke-dasharray:3 3;opacity:.55}"
    ".chart text{fill:var(--muted);font-size:11px}.chart .val{fill:var(--ink);font-weight:600}"
    ".caption{font-size:11.5px;color:var(--muted);margin:2px 0 0;max-width:760px}"
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
    # Headline highlights with the opponent (e.g. "HS 120* v Pomonal · BB 4-3 v Chalambar").
    an_ov = snap.get("analysis") or {}
    hl: list[str] = []
    for key, lbl, fld in (("best_batting", "HS", "score"), ("best_bowling", "BB", "figures")):
        top = (an_ov.get(key) or [])
        if top:
            opp = top[0].get("opposition")
            hl.append(f"{lbl} <b>{escape(str(top[0].get(fld) or ''))}</b>"
                      + (f" v {escape(str(opp))}" if opp else ""))
    if hl:
        ov.append("<p class='muted' style='margin:2px 0 8px'>" + " &nbsp;·&nbsp; ".join(hl) + "</p>")
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
        charts: list[str] = []
        runs_c = _chart_by_season(seasons, "runs", "Runs by season")
        if runs_c:
            charts.append("<h3 class='sub'>Runs by season</h3>" + runs_c)
        wkts_c = _chart_by_season(seasons, "wickets", "Wickets by season")
        if wkts_c:
            charts.append("<h3 class='sub'>Wickets by season</h3>" + wkts_c)
        table = _table(
            [("Season", ""), ("M", "r"), ("Runs", "r"), ("Bat avg", "r"), ("Wkts", "r"),
             ("Bowl avg", "r"), ("Ct", "r")], rows)
        tabs.append(("seasons", "Seasons", "".join(charts)
                     + ("<h3 class='sub'>Season by season</h3>" if charts else "") + table))

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

    _analysis_tabs(snap.get("analysis") or {}, tabs)
    _matches_tab(snap.get("matches") or [], tabs)
    return tabs


_RESULT_LABEL = {"win": "Won", "loss": "Lost", "draw": "Draw", "tie": "Tie", "no_result": "No result"}


def _matches_tab(rows: list[dict[str, Any]], tabs: list[tuple[str, str, str]]) -> None:
    """A match-by-match career log (newest first): date, opposition, ground, the player's batting and
    bowling line, catches and the match result."""
    if not rows:
        return
    trs: list[str] = []
    for m in rows:
        runs = m.get("runs")
        bat = f"{runs}{'' if m.get('out') else '*'}" if runs is not None else "—"
        wk = m.get("wickets")
        bowl = (f"{wk}-{m.get('runs_conceded') if m.get('runs_conceded') is not None else '?'}"
                if wk is not None else "—")
        ct = m.get("catches")
        cap = " <span class='muted'>(c)</span>" if m.get("captained") else ""
        trs.append("<tr><td>" + _date(m.get("match_date")) + "</td>"
                   + "<td>" + escape(str(m.get("opposition") or "—")) + cap + "</td>"
                   + "<td>" + escape(str(m.get("ground") or "—")) + "</td>"
                   + "<td class='r'>" + escape(bat) + "</td>"
                   + "<td class='r'>" + escape(bowl) + "</td>"
                   + "<td class='r'>" + (_num(ct) if ct is not None else "—") + "</td>"
                   + "<td>" + escape(_RESULT_LABEL.get(str(m.get("result")), "—")) + "</td></tr>")
    tabs.append(("matches", "Matches", _table(
        [("Date", ""), ("Opposition", ""), ("Ground", ""), ("Bat", "r"), ("Bowl", "r"),
         ("Ct", "r"), ("Result", "")], trs)))


def _analysis_tabs(an: dict[str, Any], tabs: list[tuple[str, str, str]]) -> None:
    """Append the CricketStatz-style deep-dive tabs from the whole-career analysis: best batting/bowling,
    splits (by opposition/ground/grade/format), top partnerships, and dismissal analysis."""
    # ---- Best performances ----
    bb_rows, bw_rows = an.get("best_batting") or [], an.get("best_bowling") or []
    if bb_rows or bw_rows:
        parts: list[str] = []
        if bb_rows:
            rows = [f"<tr><td class='r'>{i + 1}</td><td class='r'><b>{escape(str(r.get('score') or ''))}</b></td>"
                    f"<td>{escape(str(r.get('opposition') or '—'))}</td><td>{escape(str(r.get('ground') or '—'))}</td>"
                    f"<td>{_date(r.get('date'))}</td><td class='r'>{_num(r.get('position'))}</td></tr>"
                    for i, r in enumerate(bb_rows)]
            parts.append("<h3 class='sub'>Best batting</h3>" + _table(
                [("#", "r"), ("Score", "r"), ("Opposition", ""), ("Ground", ""), ("Date", ""), ("Pos", "r")], rows))
        if bw_rows:
            rows = [f"<tr><td class='r'>{i + 1}</td><td class='r'><b>{escape(str(r.get('figures') or ''))}</b></td>"
                    f"<td>{escape(str(r.get('opposition') or '—'))}</td><td>{escape(str(r.get('ground') or '—'))}</td>"
                    f"<td>{_date(r.get('date'))}</td></tr>"
                    for i, r in enumerate(bw_rows)]
            parts.append("<h3 class='sub'>Best bowling</h3>" + _table(
                [("#", "r"), ("Figures", "r"), ("Opposition", ""), ("Ground", ""), ("Date", "")], rows))
        tabs.append(("best", "Best", "".join(parts)))

    # ---- Charts (scores innings-by-innings + score distribution) ----
    scores = an.get("scores") or {}
    charts: list[str] = []
    sc = _chart_scores(scores.get("innings") or [])
    if sc:
        charts.append("<h3 class='sub'>Scores — innings by innings</h3>" + sc
                      + "<p class='caption'>Each bar is one innings, oldest on the left. Lighter bars are "
                        "not-out innings; the dashed lines mark 50 and 100. Hover a bar for the date and score.</p>")
    dist = _chart_distribution(scores.get("frequency") or [])
    if dist:
        charts.append("<h3 class='sub'>Score distribution</h3>" + dist
                      + "<p class='caption'>How many innings fell in each score band.</p>")
    # ---- Bowling charts (wickets innings-by-innings + wickets-per-innings distribution) ----
    spells = an.get("spells") or {}
    wk = _chart_wickets(spells.get("innings") or [])
    if wk:
        charts.append("<h3 class='sub'>Wickets — innings by innings</h3>" + wk
                      + "<p class='caption'>Each bar is one bowling innings, oldest on the left. The dashed "
                        "line marks a five-wicket haul. Hover a bar for the date and figures.</p>")
    wdist = _chart_distribution(spells.get("frequency") or [])
    if wdist:
        charts.append("<h3 class='sub'>Wickets per innings</h3>" + wdist
                      + "<p class='caption'>How many bowling innings returned each number of wickets.</p>")
    if charts:
        tabs.append(("charts", "Charts", "".join(charts)))

    # ---- Splits (by opposition / ground / grade / format) ----
    splits = an.get("splits") or {}
    sp: list[str] = []
    for dim, title, head in (("opposition", "By opposition", "Opposition"), ("ground", "By ground", "Ground"),
                             ("grade", "By grade", "Grade"), ("format", "By format", "Format")):
        s = splits.get(dim) or {}
        bat_rows, bowl_rows = s.get("batting") or [], s.get("bowling") or []
        if not bat_rows and not bowl_rows:
            continue
        sp.append(f"<h3 class='sub'>{escape(title)}</h3>")
        if bat_rows:
            rows = ["<tr><td>" + escape(str(r.get("label") or "—")) + "</td>" + "".join(
                f"<td class='r'>{v}</td>" for v in (
                    _num(r.get("matches")), _num(r.get("innings")), _num(r.get("runs")), _num(r.get("average"), 2),
                    escape(str(r.get("high_score") or "—")), _num(r.get("fifties")), _num(r.get("hundreds")))) + "</tr>"
                for r in bat_rows]
            sp.append("<p class='muted' style='margin:6px 0 2px'>Batting</p>" + _table(
                [(head, ""), ("M", "r"), ("Inns", "r"), ("Runs", "r"), ("Avg", "r"), ("HS", "r"),
                 ("50", "r"), ("100", "r")], rows))
        if bowl_rows:
            rows = ["<tr><td>" + escape(str(r.get("label") or "—")) + "</td>" + "".join(
                f"<td class='r'>{v}</td>" for v in (
                    _num(r.get("matches")), escape(str(r.get("overs") or "—")), _num(r.get("maidens")),
                    _num(r.get("runs")), _num(r.get("wickets")), _num(r.get("average"), 2),
                    _num(r.get("economy"), 2), escape(str(r.get("best") or "—")))) + "</tr>"
                for r in bowl_rows]
            sp.append("<p class='muted' style='margin:6px 0 2px'>Bowling &amp; fielding</p>" + _table(
                [(head, ""), ("M", "r"), ("Overs", "r"), ("Mdns", "r"), ("Runs", "r"), ("Wkts", "r"),
                 ("Avg", "r"), ("Econ", "r"), ("BB", "r")], rows))
    if sp:
        tabs.append(("splits", "Splits", "".join(sp)))

    # ---- Partnerships ----
    parts_rows, totals = an.get("partnerships") or [], an.get("partnership_totals") or []
    if parts_rows or totals:
        ph: list[str] = []
        if parts_rows:
            rows = [f"<tr><td class='r'>{i + 1}</td>"
                    f"<td class='r'><b>{_num(r.get('runs'))}{'*' if r.get('unbroken') else ''}</b></td>"
                    f"<td>{escape(str(r.get('partner') or '—'))}</td><td>{escape(str(r.get('opposition') or '—'))}</td>"
                    f"<td>{escape(str(r.get('ground') or '—'))}</td><td>{_date(r.get('date'))}</td></tr>"
                    for i, r in enumerate(parts_rows)]
            ph.append("<h3 class='sub'>Highest partnerships</h3>" + _table(
                [("#", "r"), ("Runs", "r"), ("Partner", ""), ("Opposition", ""), ("Ground", ""), ("Date", "")], rows))
        if totals:
            rows = ["<tr><td>" + escape(str(r.get("partner") or "—")) + "</td>" + "".join(
                f"<td class='r'>{v}</td>" for v in (
                    _num(r.get("runs")), _num(r.get("stands")), _num(r.get("best")), _num(r.get("average"), 2))) + "</tr>"
                for r in totals]
            ph.append("<h3 class='sub'>Most runs added with</h3>" + _table(
                [("Partner", ""), ("Runs", "r"), ("Stands", "r"), ("Best", "r"), ("Avg", "r")], rows))
        tabs.append(("partnerships", "Partnerships", "".join(ph)))

    # ---- Dismissals ----
    dis = an.get("dismissals") or {}
    how, by = dis.get("how_out") or [], dis.get("dismissed_by") or []
    if how or by:
        dh: list[str] = []
        if how:
            rows = ["<tr><td>" + escape(str(r.get("type") or "").title()) + "</td><td class='r'>"
                    + _num(r.get("count")) + "</td></tr>" for r in how]
            dh.append("<h3 class='sub'>How out</h3>" + _table([("Dismissal", ""), ("Count", "r")], rows))
        if by:
            rows = ["<tr><td>" + escape(str(r.get("player") or "—")) + "</td><td class='r'>"
                    + _num(r.get("count")) + "</td></tr>" for r in by]
            dh.append("<h3 class='sub'>Most often dismissed by</h3>" + _table([("Bowler", ""), ("Times", "r")], rows))
        tabs.append(("dismissals", "Dismissals", "".join(dh)))


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
    # Club crest for the hero: the workspace branding logo, else the player's primary club's own crest —
    # so an uploaded club logo shows even when no workspace-wide branding logo is set.
    logo = brand.get("logo") or next((cl.get("crest") for cl in (snap.get("clubs") or []) if cl.get("crest")), None)
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

    # Honour-grade recognitions (Life Member, honorary member, …) and awarded honour badges lead the hero
    # as gold badges, so the player's standing is visible on every tab — not only on the Overview/Honours
    # panel. These are the player's own recognition, kept on club-scoped profiles too.
    hon_labels: list[str] = []
    for r in (det.get("recognition") or []):
        lab = str(r.get("label") or "").strip()
        if lab and lab not in hon_labels:
            hon_labels.append(lab)
    for x in ((snap.get("badges") or {}).get("awarded") or []):
        lab = str(x.get("label") or "").strip()
        if lab and lab not in hon_labels:
            hon_labels.append(lab)
    honours_html = ("<div class='honours'>"
                    + "".join(f"<span class='hon-badge'>★ {escape(lab)}</span>" for lab in hon_labels)
                    + "</div>") if hon_labels else ""

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
        f"<div class='id'><div class='club'>{club_mark}{club}</div><h1>{name}</h1>{chips_html}{honours_html}{meta_html}</div>"
        f"<div class='keys'>{key_cells}</div></div></header>"
        f"<nav class='tabs' role='tablist'>{tabbar}</nav>"
        f"<main>{panels}{('<div>' + notes + '</div>') if notes else ''}</main>"
        f"<footer>Published by OneStats · {gen}{foot_link} · Approved statistics only — "
        "unknown values are never shown as zero.</footer>"
        f"<script>{_PROFILE_JS}</script></body></html>")


def _render_html(snap: dict[str, Any], title: str, public_base: str, slug: str) -> str:
    # Player profiles get the rich, tab-through page; reports get a branded single-table page. Both share
    # the same theme-aware styling.
    if snap.get("kind") == "player_profile":
        return _render_profile_page(snap, title, public_base, slug)
    return _render_report_page(snap, title, public_base, slug)


def _render_report_page(snap: dict[str, Any], title: str, public_base: str, slug: str) -> str:
    """A branded, theme-aware published report page: a hero with the club crest and report title, then the
    report table in the shared styling. Self-contained; approved public data only."""
    brand = snap.get("branding") or {}
    primary = escape(str(brand.get("primary") or "#0b5e3b"))
    accent = escape(str(brand.get("accent") or brand.get("secondary") or brand.get("primary") or "#0b5e3b"))
    club = escape(str(brand.get("club") or "OneStats"))
    logo = brand.get("logo")
    theme = str(brand.get("theme") or "system")
    theme_class = "theme-" + (theme if theme in ("light", "dark") else "system")
    gen = datetime.now(UTC).strftime("%d %b %Y")

    cols, rows = snap.get("columns") or [], snap.get("rows") or []
    head = "".join(f"<th class='{'r' if c['align'] == 'right' else ''}'>{escape(c['label'])}</th>" for c in cols)
    trs = []
    for r in rows:
        tds = []
        for c in cols:
            v = r.get(c["key"])
            s = ("—" if v is None else (f"{v:.{c['decimals']}f}" if c["decimals"] is not None and isinstance(v, (int, float))
                 else ("Yes" if v is True else "No" if v is False else escape(str(v)))))
            tds.append(f"<td class='{'r' if c['align'] == 'right' else ''}'>{s}</td>")
        trs.append("<tr>" + "".join(tds) + "</tr>")
    table_html = (f"<div class='tbl'><table><thead><tr>{head}</tr></thead><tbody>{''.join(trs)}</tbody></table></div>"
                  if rows else "<p class='muted'>No published data for this report yet.</p>")
    notes = "".join(f"<p class='muted'>{escape(q)}</p>" for q in snap.get("qualifications", []))

    crest = (f"<div class='avatar crest'><img src='{logo}' alt='{club} logo'></div>" if logo
             else f"<div class='avatar mono'>{escape((brand.get('club') or 'R')[:1].upper())}</div>")
    foot_link = (" · " + escape(public_base) + "/r/" + escape(slug)) if public_base else ""
    rowcount = f"{len(rows)} row{'s' if len(rows) != 1 else ''} · {gen}"
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{escape(title)} — {club}</title>"
        f"<style>:root{{--brand:{primary};--accent:{accent}}}</style>"
        f"<style>{_PROFILE_CSS}</style></head><body class='{theme_class}'>"
        f"<header class='hero'><div class='hero-in'>{crest}"
        f"<div class='id'><div class='club'>{club}</div><h1>{escape(title)}</h1>"
        f"<div class='meta'>{escape(rowcount)}</div></div></div></header>"
        f"<main>{table_html}{notes}</main>"
        f"<footer>Published by OneStats · {gen}{foot_link} · Approved statistics only — "
        "unknown values are never shown as zero.</footer></body></html>")


def _snapshot(conn: Connection, settings: Settings, workspace_id: UUID, row: dict[str, Any]) -> dict[str, Any]:
    brand = _branding(conn, workspace_id)
    if row["kind"] == "report":
        snap = _report_snapshot(conn, workspace_id, row["report_id"], row.get("filters") or {}, brand, settings)
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


def delete_publication(conn: Connection, workspace_id: UUID, actor: str, pub_id: UUID) -> dict[str, Any]:
    """Permanently remove a publication (its row and stored snapshot). Unlike unpublish/revoke — which
    keep the record but stop it serving — this deletes it entirely, so it leaves the manage list. The
    public URL stops resolving at once; a file already on a static host is dropped on the next whole-site
    publish/export (that mirror no longer includes it)."""
    row = _row(conn, workspace_id, pub_id)
    if row is None:
        raise ValueError("publication_not_found")
    conn.execute(text("DELETE FROM publication WHERE id = :id AND workspace_id = :w"),
                 {"id": pub_id, "w": workspace_id})
    audit.write_audit(conn, workspace_id, actor, "publication.delete", entity="publication",
                      entity_id=str(pub_id),
                      before={"kind": row["kind"], "slug": row["slug"], "title": row["title"]})
    return {"id": str(pub_id), "deleted": True}


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
