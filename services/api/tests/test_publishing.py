"""Website publishing (Phase 15) — hosting-neutral: publish a report/profile, serve the snapshot publicly
with no workspace context (offline-capable), privacy-filter profiles, publish/unpublish/revoke, static
export, automatic-staleness on stat change, and workspace isolation. Requires a live DB; rolled back.
"""
from __future__ import annotations

import json
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import Settings, get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting, competitions, matches, people, publishing
from onestats.domain import innings as inn

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"
TS = Settings(env="test", db_password=None, _env_file=None)


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


def _ws(conn, name):
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES (:n,'club') RETURNING id"), {"n": name}).scalar_one()
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a, 'pub') ON CONFLICT (id) DO NOTHING"), {"a": ACTOR})
    set_workspace(conn, wid)
    return wid


def _team(conn, wid, name):
    org = conn.execute(text("INSERT INTO organisation(workspace_id,name,kind) VALUES (:w,:n,'club') RETURNING id"),
                       {"w": wid, "n": name + " CC"}).scalar_one()
    return conn.execute(text("INSERT INTO team(workspace_id,organisation_id,name) VALUES (:w,:o,:n) RETURNING id"),
                        {"w": wid, "o": org, "n": name}).scalar_one()


def _match(conn, wid, comp, se, home, away, p, runs):
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=se)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=p, batting_position=1, runs=runs, dismissal_type="bowled")
    matches.set_result(conn, wid, ACTOR, mid, result_type="home_win", won_by_team_id=home)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    return mid


def _no_context(conn):
    """Clear the workspace GUC to emulate the public (unauthenticated) read path."""
    conn.execute(text("SELECT set_config('onestats.workspace_id', '', true)"))


def _snap(conn, pub_id):
    """Read a publication's stored snapshot as a dict (admin read; keeps workspace context intact)."""
    s = conn.execute(text("SELECT snapshot FROM publication WHERE id = :i"), {"i": pub_id}).scalar_one()
    return s if isinstance(s, dict) else json.loads(s)


@pytest.fixture
def seeded(conn):
    wid = _ws(conn, "PUB")
    comp = competitions.create_competition(conn, wid, ACTOR, name="League")
    se = conn.execute(text("INSERT INTO season(workspace_id,competition_id,label,start_date) "
                           "VALUES (:w,:c,'2024/25','2024-10-01') RETURNING id"), {"w": wid, "c": comp}).scalar_one()
    home, away = _team(conn, wid, "Rhymney"), _team(conn, wid, "Away")
    p = people.create_person(conn, wid, ACTOR, display_name="Star Player")
    _match(conn, wid, comp, se, home, away, p, 100)
    return {"wid": wid, "comp": comp, "se": se, "home": home, "away": away, "p": p}


def test_publish_report_and_serve_public(seeded, conn):
    wid = seeded["wid"]
    pub = publishing.create_publication(conn, TS, wid, ACTOR, kind="report", title="Leading Run Scorers",
                                        report_id="bat_most_runs")
    assert pub["slug"] and pub["status"] == "published" and pub["snapshot"] is not None
    # public read with NO workspace context resolves the snapshot by slug
    _no_context(conn)
    got = publishing.get_public(conn, pub["slug"])
    assert got is not None and got["kind"] == "report"
    rows = got["snapshot"]["rows"] if isinstance(got["snapshot"], dict) else json.loads(got["snapshot"])["rows"]
    assert rows[0]["player"] == "Star Player" and rows[0]["runs"] == 100


def test_unpublish_and_revoke_stop_serving(seeded, conn):
    wid = seeded["wid"]
    pub = publishing.create_publication(conn, TS, wid, ACTOR, kind="report", title="R", report_id="bat_most_runs")
    slug = pub["slug"]
    publishing.set_status(conn, wid, ACTOR, pub["id"], "unpublished")
    _no_context(conn); assert publishing.get_public(conn, slug) is None
    set_workspace(conn, wid)
    publishing.set_status(conn, wid, ACTOR, pub["id"], "published")
    _no_context(conn); assert publishing.get_public(conn, slug) is not None
    set_workspace(conn, wid)
    publishing.set_status(conn, wid, ACTOR, pub["id"], "revoked")
    _no_context(conn); assert publishing.get_public(conn, slug) is None


def test_offline_last_good_snapshot_and_stale_refresh(seeded, conn):
    """A stat change marks the publication stale but the public snapshot keeps serving the last good copy
    until a refresh regenerates it (offline-capable, never goes dark)."""
    d = seeded
    wid = d["wid"]
    pub = publishing.create_publication(conn, TS, wid, ACTOR, kind="report", title="R", report_id="bat_most_runs")
    slug = pub["slug"]
    # approve another match → the player now has 150, and publications are flagged stale
    _match(conn, wid, d["comp"], d["se"], d["home"], d["away"], d["p"], 50)
    stale = conn.execute(text("SELECT stale FROM publication WHERE id = :i"), {"i": pub["id"]}).scalar_one()
    assert stale is True
    # public still serves the LAST good snapshot (100), not the new total
    _no_context(conn)
    rows = publishing.get_public(conn, slug)["snapshot"]["rows"]
    assert rows[0]["runs"] == 100
    # refresh regenerates; now public serves 150 and stale is cleared
    set_workspace(conn, wid)
    assert publishing.refresh_workspace(conn, TS, wid, ACTOR)["refreshed"] == 1
    assert conn.execute(text("SELECT stale FROM publication WHERE id = :i"), {"i": pub["id"]}).scalar_one() is False
    _no_context(conn)
    assert publishing.get_public(conn, slug)["snapshot"]["rows"][0]["runs"] == 150


def test_static_export_files(seeded, conn):
    wid = seeded["wid"]
    pub = publishing.create_publication(conn, TS, wid, ACTOR, kind="report", title="Leading Run Scorers",
                                        report_id="bat_most_runs")
    files = publishing.static_export(conn, wid, pub["id"])
    html = files[f"{pub['slug']}.html"]
    assert f"{pub['slug']}.json" in files and f"{pub['slug']}.html" in files
    assert "<table" in html and "Star Player" in html and "PUB" in html   # table + club header
    assert json.loads(files[f"{pub['slug']}.json"])["title"] == "Leading Run Scorers"


def test_public_profile_excludes_private_data(seeded, conn):
    wid, p = seeded["wid"], seeded["p"]
    # give the person a date of birth (private) — it must never appear in the public snapshot
    conn.execute(text("UPDATE person SET dob = '1990-01-01', dob_precision = 'exact' WHERE id = :p"), {"p": p})
    pub = publishing.create_publication(conn, TS, wid, ACTOR, kind="player_profile", title="Star Player", person_id=p)
    _no_context(conn)
    got = publishing.get_public(conn, pub["slug"])
    blob = json.dumps(got["snapshot"] if isinstance(got["snapshot"], dict) else json.loads(got["snapshot"]))
    assert got["kind"] == "player_profile" and "Star Player" in blob
    assert "1990-01-01" not in blob               # the private DOB is never published


def test_mobile_portal_lists_published_only(seeded, conn):
    """Phase 16: the public mobile portal index lists published items (no workspace context) and excludes
    unpublished/revoked, independent of the live DB (snapshot-based)."""
    wid = seeded["wid"]
    r1 = publishing.create_publication(conn, TS, wid, ACTOR, kind="report", title="Leading Run Scorers", report_id="bat_most_runs")
    r2 = publishing.create_publication(conn, TS, wid, ACTOR, kind="report", title="Most Wickets", report_id="bowl_most_wickets")
    publishing.set_status(conn, wid, ACTOR, r2["id"], "unpublished")   # should not appear in the portal
    _no_context(conn)
    portal = publishing.public_portal(conn, wid)
    titles = [i["title"] for i in portal["items"]]
    assert "Leading Run Scorers" in titles and "Most Wickets" not in titles
    assert portal["club"] == "PUB"                                     # branding from the snapshot
    html = publishing.render_portal_html(portal)
    assert "Leading Run Scorers" in html and "PUB — Records" in html and "viewport" in html
    assert r1["slug"] in html


def test_member_portal_includes_non_public_items(seeded, conn):
    """Phase 16 follow-up: the authenticated member portal lists public published items PLUS the non-public
    (unpublished) catalogue, each flagged — and excludes revoked. Branding/club come from the workspace."""
    wid = seeded["wid"]
    publishing.create_publication(conn, TS, wid, ACTOR, kind="report", title="Public Report", report_id="bat_most_runs")
    draft = publishing.create_publication(conn, TS, wid, ACTOR, kind="report", title="Draft Report", report_id="bowl_most_wickets")
    publishing.set_status(conn, wid, ACTOR, draft["id"], "unpublished")
    gone = publishing.create_publication(conn, TS, wid, ACTOR, kind="player_profile", title="Gone", person_id=seeded["p"])
    publishing.set_status(conn, wid, ACTOR, gone["id"], "revoked")

    portal = publishing.member_portal(conn, wid)
    by_title = {i["title"]: i for i in portal["items"]}
    assert by_title["Public Report"]["public"] is True and by_title["Public Report"]["path"]
    assert by_title["Draft Report"]["public"] is False and by_title["Draft Report"]["path"] is None
    assert "Gone" not in by_title                                   # revoked never appears
    assert portal["public_count"] == 1 and portal["member_only_count"] == 1
    assert portal["club"] == "PUB"


def test_profile_publish_scoped_to_one_club_excludes_other_clubs_and_shows_badges(seeded, conn):
    """A club-scoped published profile shows ONLY that club's statistics — a player's runs for other clubs
    are excluded from the career figures AND from every report (season line, deep analysis, match list), so
    a single-club profile carries the full reports for that club alone without ever leaking another club's
    figures. All-time records held (workspace-wide) are the one section omitted. The scope is labelled and
    the badges are carried. The whole-career profile counts every club."""
    d = seeded; wid = d["wid"]; p = d["p"]
    rhymney_org = conn.execute(text("SELECT organisation_id FROM team WHERE id = :t"), {"t": d["home"]}).scalar_one()
    # the same player also turns out for another club and scores 50 there — must NOT appear on the Rhymney profile
    other_team = _team(conn, wid, "Moyston")
    _match(conn, wid, d["comp"], d["se"], other_team, d["away"], p, 50)

    # whole career: both clubs counted (100 + 50), season-by-season present, no scope label
    career = publishing.create_publication(conn, TS, wid, ACTOR, kind="player_profile", title="Star Player", person_id=p)
    sa = _snap(conn, career["id"])
    assert sa["career"]["batting"]["runs"] == 150
    assert not sa.get("scope_club")
    assert len(sa["seasons"]) >= 1

    # scoped to Rhymney: every report present but restricted to its 100 — the other club's 50 appears nowhere
    scoped = publishing.create_publication(conn, TS, wid, ACTOR, kind="player_profile", title="Star Player",
                                           person_id=p, filters={"organisation_id": str(rhymney_org)})
    ss = _snap(conn, scoped["id"])
    assert ss["career"]["batting"]["runs"] == 100          # the other club's 50 is excluded
    assert ss["scope_club"]                                 # labelled with the club it is published for
    assert ss["records"] == []                             # all-time records held are workspace-wide -> omitted
    # the reports are now club-scoped rather than omitted, and reflect the 100 only (never the 50)
    assert [i["runs"] for i in ss["analysis"]["scores"]["innings"]] == [100]
    assert all(m["runs"] != 50 for m in ss["matches"]) and any(m["runs"] == 100 for m in ss["matches"])
    assert len(ss["seasons"]) >= 1 and ss["seasons"][0]["runs"] == 100
    assert "badges" in ss                                  # badges carried into the published export
    html = conn.execute(text("SELECT snapshot_html FROM publication WHERE id = :i"), {"i": scoped["id"]}).scalar_one()
    assert "only" in html.lower()                          # the "Statistics for … only" note is rendered


def test_publish_profile_rejects_unknown_club(seeded, conn):
    import uuid
    with pytest.raises(ValueError, match="unknown_organisation"):
        publishing.create_publication(conn, TS, seeded["wid"], ACTOR, kind="player_profile", title="X",
                                      person_id=seeded["p"], filters={"organisation_id": str(uuid.uuid4())})


def test_public_base_url_validation_and_storage(seeded, conn):
    wid = seeded["wid"]
    assert publishing.get_public_base_url(conn, wid) is None
    with pytest.raises(ValueError, match="invalid_base_url"):
        publishing.set_public_base_url(conn, wid, ACTOR, "ftp://nope")
    # a valid https address is stored with the trailing slash normalised away
    assert publishing.set_public_base_url(conn, wid, ACTOR, "https://rmcc.github.io/stats/") == "https://rmcc.github.io/stats"
    assert publishing.get_public_base_url(conn, wid) == "https://rmcc.github.io/stats"
    assert publishing.set_public_base_url(conn, wid, ACTOR, "   ") is None   # blank clears it


def test_site_export_whole_site(seeded, conn):
    wid = seeded["wid"]
    pub = publishing.create_publication(conn, TS, wid, ACTOR, kind="report", title="Leading Run Scorers",
                                        report_id="bat_most_runs")
    files = publishing.site_export(conn, wid)
    # the bundle carries the static-host markers and each published report under r/
    assert ".nojekyll" in files and "index.html" in files and "README.txt" in files
    assert f"r/{pub['slug']}.html" in files and f"r/{pub['slug']}.json" in files
    assert "Star Player" in files[f"r/{pub['slug']}.html"]
    # the index links to the report by its relative static path and carries the club name
    assert f"r/{pub['slug']}.html" in files["index.html"] and "PUB" in files["index.html"]
    assert json.loads(files[f"r/{pub['slug']}.json"])["title"] == "Leading Run Scorers"


def test_public_urls_static_layout():
    from onestats.api.v1 import publications as papi
    rows = [{"kind": "report", "slug": "abc"}, {"kind": "player_profile", "slug": "xyz"}]
    out = papi._public_urls(TS, "https://host/site/", rows)
    assert out[0]["public_url"] == "https://host/site/r/abc.html" and out[0]["json_url"] == "https://host/site/r/abc.json"
    assert out[1]["public_url"] == "https://host/site/p/xyz.html"
    # no configured host → no live URL (download-and-upload only)
    assert papi._public_urls(TS, None, [{"kind": "report", "slug": "abc"}])[0]["public_url"] is None


def test_isolation_admin_cannot_see_other_workspace(seeded, conn):
    wid = seeded["wid"]
    pub = publishing.create_publication(conn, TS, wid, ACTOR, kind="report", title="R", report_id="bat_most_runs")
    other = _ws(conn, "PUB OTHER")                     # switches workspace context to the other workspace
    assert publishing.list_publications(conn, other) == []   # admin of B sees none of A's
    # but the public edge (no context) can still serve A's published snapshot (intended)
    _no_context(conn)
    assert publishing.get_public(conn, pub["slug"]) is not None


def test_profile_html_is_a_tabbed_branded_page(seeded, conn):
    """The published player profile is the rich, tab-through page: a branded hero and clickable
    discipline tabs, fully self-contained (styles and script inlined, no external assets). The seeded
    player has batting, so a Batting tab appears alongside Overview."""
    wid = seeded["wid"]
    pub = publishing.create_publication(conn, TS, wid, ACTOR, kind="player_profile",
                                        title="Star Player", person_id=seeded["p"])
    html = conn.execute(text("SELECT snapshot_html FROM publication WHERE id = :i"),
                        {"i": pub["id"]}).scalar_one()
    assert "class='hero'" in html and "Star Player" in html
    assert "class='tabs'" in html and "data-target='t_overview'" in html
    assert "data-target='t_batting'" in html          # the seeded player batted -> a Batting tab
    assert "<script>" in html and "<style>" in html   # self-contained: no external CSS/JS/images


def test_profile_photo_embedded_only_when_public(seeded, conn, monkeypatch):
    """A player's photo appears on the public profile ONLY when it is marked public_visible; a private
    photo is never published. When shown, it is inlined as a data: URI (never an external link)."""
    from onestats.domain import profiles as _profiles
    wid, p = seeded["wid"], seeded["p"]
    # pretend a stored file exists and inlines to a sentinel data URI (no real media needed here)
    monkeypatch.setattr(publishing.photos, "photo_path", lambda s, w, k: object())
    monkeypatch.setattr(publishing, "_file_data_uri",
                        lambda path, **k: "data:image/png;base64,AAAA" if path else None)
    _profiles.register_photo(conn, wid, ACTOR, p, media_key="x.png", is_primary=True, public_visible=False)
    assert publishing._public_photo_data_uri(conn, TS, wid, p) is None        # private -> not selected
    conn.execute(text("UPDATE person_photo SET public_visible = true WHERE person_id = :p"), {"p": p})
    assert publishing._public_photo_data_uri(conn, TS, wid, p) == "data:image/png;base64,AAAA"


def test_profile_theme_class_follows_branding(seeded, conn):
    """The published profile carries the club's selected theme (light/dark/system), so its colours match
    the configured branding rather than a fixed default."""
    from onestats.domain import branding as _branding
    wid, p = seeded["wid"], seeded["p"]
    pub = publishing.create_publication(conn, TS, wid, ACTOR, kind="player_profile",
                                        title="Star Player", person_id=p)
    html = conn.execute(text("SELECT snapshot_html FROM publication WHERE id = :i"),
                        {"i": pub["id"]}).scalar_one()
    assert "theme-system" in html                                   # no theme set -> follow the viewer
    _branding.set_branding(conn, wid, UUID(ACTOR), {"theme_mode": "dark", "primary_colour": "#0b5e3b"})
    publishing.republish(conn, TS, wid, ACTOR, pub["id"])
    html2 = conn.execute(text("SELECT snapshot_html FROM publication WHERE id = :i"),
                         {"i": pub["id"]}).scalar_one()
    assert "theme-dark" in html2 and "#0b5e3b" in html2             # club theme + colour applied


def test_profile_recognition_becomes_an_honour_badge():
    """A recognition such as Life Member appears as a prominent honour badge on the published profile,
    not only buried in the service list."""
    snap = {
        "kind": "player_profile", "person_name": "Honoured Player", "title": "Honoured Player",
        "branding": {"club": "RMCC", "primary": "#0b5e3b"},
        "detail": {"recognition": [{"label": "Life Member", "seasons": ["2016"]}], "leadership": [], "numbers": []},
        "career": {"matches": 10, "batting": {}, "bowling": {}, "fielding": {}, "captaincy": {}},
        "badges": {"calculated": [], "awarded": []}, "qualifications": [],
    }
    html = publishing._render_profile_page(snap, "Honoured Player", "", "slug")
    assert "badge hon" in html and "Life Member" in html
    # Also a prominent gold honour badge in the hero, so it shows on every tab (not only Overview/Honours).
    assert "hon-badge" in html and html.count("Life Member") >= 2


def test_published_badges_collapse_to_the_highest_in_each_ladder():
    """The published badge row keeps only the top milestone reached in each ladder (one 'career runs',
    one 'career wickets', …), while count badges (N× Century / Five-Wicket Innings / Hat-trick) are each
    distinct achievements and all kept."""
    cal = [
        {"label": "100 career runs", "category": "runs"}, {"label": "1000 career runs", "category": "runs"},
        {"label": "5000 career runs", "category": "runs"}, {"label": "50 career wickets", "category": "wickets"},
        {"label": "300 career wickets", "category": "wickets"}, {"label": "25 matches played", "category": "matches"},
        {"label": "300 matches played", "category": "matches"}, {"label": "2× Century", "category": "batting"},
        {"label": "4× Five-Wicket Innings", "category": "bowling"}, {"label": "1× Hat-trick", "category": "bowling"},
    ]
    out = [b["label"] for b in publishing._collapse_badge_ladders(cal)]
    assert out == ["5000 career runs", "300 career wickets", "300 matches played",
                   "2× Century", "4× Five-Wicket Innings", "1× Hat-trick"]


def test_delete_publication_removes_it_entirely(seeded, conn):
    """Delete permanently removes a publication (row + snapshot) — unlike unpublish/revoke, which keep the
    record. It leaves the manage list and its public slug stops resolving; deleting again is not-found."""
    wid = seeded["wid"]
    pub = publishing.create_publication(conn, TS, wid, ACTOR, kind="report", title="Gone Soon", report_id="bat_most_runs")
    slug = pub["slug"]
    assert any(str(p["id"]) == str(pub["id"]) for p in publishing.list_publications(conn, wid))
    publishing.delete_publication(conn, wid, ACTOR, pub["id"])
    assert all(str(p["id"]) != str(pub["id"]) for p in publishing.list_publications(conn, wid))
    _no_context(conn)
    assert publishing.get_public(conn, slug) is None
    set_workspace(conn, wid)
    with pytest.raises(ValueError, match="publication_not_found"):
        publishing.delete_publication(conn, wid, ACTOR, pub["id"])


def test_profile_includes_deep_analysis_tabs_whole_career(seeded, conn):
    """A whole-career profile carries the CricketStatz-style deep tabs — Best performances, Splits and
    the rest — built from the analysis engine, embedded in the snapshot."""
    wid = seeded["wid"]
    pub = publishing.create_publication(conn, TS, wid, ACTOR, kind="player_profile",
                                        title="Star Player", person_id=seeded["p"])
    html = conn.execute(text("SELECT snapshot_html FROM publication WHERE id = :i"),
                        {"i": pub["id"]}).scalar_one()
    assert "data-target='t_best'" in html and "data-target='t_splits'" in html
    snap = _snap(conn, pub["id"])
    assert snap["analysis"] is not None and snap["analysis"]["best_batting"]


def test_profile_includes_match_log(seeded, conn):
    """A whole-career profile carries a match-by-match log (Matches tab) with each match's opposition,
    ground and result — enriched from match_history."""
    wid = seeded["wid"]
    pub = publishing.create_publication(conn, TS, wid, ACTOR, kind="player_profile",
                                        title="Star Player", person_id=seeded["p"])
    html = conn.execute(text("SELECT snapshot_html FROM publication WHERE id = :i"),
                        {"i": pub["id"]}).scalar_one()
    assert "data-target='t_matches'" in html
    ms = _snap(conn, pub["id"])["matches"]
    assert ms and all(k in ms[0] for k in ("opposition", "ground", "result", "match_date"))


def test_score_charts_render_self_contained_svg():
    """The profile charts are self-contained inline SVG: a not-out innings is tagged for the lighter fill
    and tooltipped with a star, and the distribution labels each band's count."""
    sc = publishing._chart_scores([
        {"date": "2020-01-01", "runs": 10, "not_out": False},
        {"date": "2020-02-01", "runs": 120, "not_out": True},
    ])
    assert sc.startswith("<svg") and "class='bar no'" in sc and "120*" in sc and "<title>" in sc
    dist = publishing._chart_distribution([{"range": "0-9", "count": 3}, {"range": "100+", "count": 1}])
    assert dist.startswith("<svg") and ">3<" in dist and "0-9" in dist
    assert publishing._chart_scores([]) == "" and publishing._chart_distribution([]) == ""


def test_wicket_chart_renders_self_contained_svg():
    """The bowling chart is self-contained inline SVG: a five-wicket reference line, and each bar tooltips
    the date and figures. It needs at least two recorded spells."""
    wk = publishing._chart_wickets([
        {"date": "2020-01-01", "wickets": 2, "runs": 30},
        {"date": "2020-02-01", "wickets": 5, "runs": 12},
    ])
    assert wk.startswith("<svg") and "class='ref'" in wk and "5-12" in wk and "<title>" in wk
    assert publishing._chart_wickets([]) == ""
    assert publishing._chart_wickets([{"date": "2020-01-01", "wickets": 3, "runs": 20}]) == ""  # needs ≥2


def test_by_season_chart_labels_peak_and_guards_short_input():
    """The by-season chart directly labels the peak season and tooltips every bar; it needs at least two
    seasons with data."""
    seasons = [{"label": "2020/21", "runs": 100, "wickets": 5}, {"label": "2021/22", "runs": 300, "wickets": 2}]
    rc = publishing._chart_by_season(seasons, "runs", "Runs by season")
    assert rc.startswith("<svg") and ">300<" in rc and "2021/22: 300" in rc           # peak label + tooltip
    assert publishing._chart_by_season([{"label": "x", "runs": 10}], "runs", "x") == ""  # needs >= 2
