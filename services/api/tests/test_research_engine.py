"""Internet Research Engine — jobs, run-step orchestration, resume and isolation.

Rolled back per test; skipped without a live DB. Fully offline: discovery is a fixed list and page
retrieval uses an httpx.MockTransport, so no network is touched. Verifies: duplicate-job suppression,
findings persisted for relevant pages, content-dedup, honest fetch provenance (blocked recorded, not a
silent 'nothing found'), resume-after-interrupt without duplicating work, pause/resume/cancel, that
nothing is auto-approved, and workspace isolation.
"""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.research import engine as reng
from onestats.domain.research import jobs
from onestats.domain.research.webfetch import Fetcher

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "22222222-2222-2222-2222-222222222222"
PUBLIC_IP = "93.184.216.34"


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
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES (:n,'club') RETURNING id"),
                       {"n": name}).scalar_one()
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a, :u) ON CONFLICT (id) DO NOTHING"),
                 {"a": ACTOR, "u": f"actor-{name}"})
    set_workspace(conn, wid)
    return wid


def _page(body: str) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/html"}, text=body)


SCORECARD = "<html><title>Rhymney v Moyston 1905</title><body><pre>J Smith c b 34\nA Walker not out 21\nT Bonner lbw b 7\nR Davies run out 2</pre><p>Rhymney 112 all out, won by 14 runs</p></body></html>"


def _fetcher(handler, resolver=None) -> Fetcher:
    return Fetcher(resolver=resolver or (lambda h: [PUBLIC_IP]),
                   transport=httpx.MockTransport(handler), respect_robots=False)


def _discovery(urls):
    return lambda queries, context: [{"url": u, "source": "test"} for u in urls]


def test_duplicate_job_suppression(conn):
    wid = _ws(conn, "ENG_DUP")
    job = jobs.create_job(conn, wid, ACTOR, query="Rhymney 1905", depth="quick", context={"club": "Rhymney"})
    assert job["status"] == "pending"
    with pytest.raises(ValueError, match="duplicate_active_job"):
        jobs.create_job(conn, wid, ACTOR, query="Rhymney 1905", depth="quick", context={"club": "Rhymney"})
    # a different subject is allowed
    jobs.create_job(conn, wid, ACTOR, query="Moyston 1906", depth="quick")


def test_run_step_produces_findings_and_completes(conn):
    wid = _ws(conn, "ENG_RUN")
    job = jobs.create_job(conn, wid, ACTOR, query="Rhymney cricket", depth="quick")
    claimed = jobs.claim_next_job(conn, wid, ACTOR)

    urls = [f"https://example.com/match/{i}" for i in range(3)]
    def handler(req): return _page(SCORECARD.replace("1905", f"190{req.url.path[-1]}"))
    disc = _discovery(urls)
    fetcher = _fetcher(handler)

    done = False
    guard = 0
    while not done and guard < 10:
        guard += 1
        job = jobs.get_job(conn, claimed["id"])
        res = reng.run_step(conn, wid, ACTOR, job, settings=settings, page_fetcher=fetcher, discovery=disc)
        done = res["done"]
    assert done is True
    findings = jobs.list_findings(conn, wid)
    assert len(findings) == 3
    # nothing auto-approved; with no existing matches, team-naming findings classify as "new"
    assert all(f["status"] == "pending_review" for f in findings)
    assert all(f["classification"] in ("new", "unknown") for f in findings)
    # fetch provenance recorded
    n_fetched = conn.execute(text("SELECT count(*) FROM research_fetch WHERE job_id = :j AND outcome='fetched'"),
                             {"j": claimed["id"]}).scalar_one()
    assert n_fetched == 3


def test_identical_content_deduplicated(conn):
    wid = _ws(conn, "ENG_DEDUP")
    jobs.create_job(conn, wid, ACTOR, query="dupes", depth="quick")
    claimed = jobs.claim_next_job(conn, wid, ACTOR)
    urls = ["https://example.com/a", "https://example.com/b"]  # same content on both
    def handler(req): return _page(SCORECARD)
    reng.run_step(conn, wid, ACTOR, jobs.get_job(conn, claimed["id"]), settings=settings,
                  page_fetcher=_fetcher(handler), discovery=_discovery(urls))
    findings = jobs.list_findings(conn, wid)
    assert len(findings) == 1  # identical content → one finding
    dup = conn.execute(text("SELECT count(*) FROM research_fetch WHERE job_id = :j AND outcome='duplicate'"),
                       {"j": claimed["id"]}).scalar_one()
    assert dup == 1


def test_blocked_target_is_recorded_not_silent(conn):
    wid = _ws(conn, "ENG_BLOCK")
    jobs.create_job(conn, wid, ACTOR, query="ssrf", depth="quick")
    claimed = jobs.claim_next_job(conn, wid, ACTOR)
    # discovery yields an internal URL; the fetcher's resolver maps it to a private IP → blocked
    def resolver(host): return ["10.0.0.9"] if host == "internal.example" else [PUBLIC_IP]
    def handler(req): return _page(SCORECARD)
    reng.run_step(conn, wid, ACTOR, jobs.get_job(conn, claimed["id"]), settings=settings,
                  page_fetcher=_fetcher(handler, resolver=resolver),
                  discovery=_discovery(["https://internal.example/secret"]))
    assert jobs.list_findings(conn, wid) == []
    blocked = conn.execute(text("SELECT outcome FROM research_fetch WHERE job_id = :j"),
                           {"j": claimed["id"]}).scalar_one()
    assert blocked == "blocked"


def test_resume_after_interrupt_no_duplicate_work(conn):
    wid = _ws(conn, "ENG_RESUME")
    jobs.create_job(conn, wid, ACTOR, query="resume", depth="standard")
    claimed = jobs.claim_next_job(conn, wid, ACTOR)
    urls = [f"https://example.com/p/{i}" for i in range(7)]  # > STEP_BATCH(5) → needs 2 steps
    def handler(req): return _page(SCORECARD.replace("Rhymney", f"Team{req.url.path[-1]}"))
    disc, fetcher = _discovery(urls), _fetcher(handler)

    res1 = reng.run_step(conn, wid, ACTOR, jobs.get_job(conn, claimed["id"]), settings=settings,
                         page_fetcher=fetcher, discovery=disc)
    assert res1["done"] is False and res1["examined"] == 5

    # simulate a crash: lease expires, reconcile marks it interrupted, then it is re-claimed
    conn.execute(text("UPDATE research_job SET lease_expires_at = now() - interval '5 min' WHERE id = :id"),
                 {"id": claimed["id"]})
    rec = jobs.reconcile_stale_jobs(conn, wid, ACTOR)
    assert rec["requeued"] == 1
    reclaim = jobs.claim_next_job(conn, wid, ACTOR)
    assert reclaim is not None

    res2 = reng.run_step(conn, wid, ACTOR, jobs.get_job(conn, reclaim["id"]), settings=settings,
                         page_fetcher=fetcher, discovery=disc)
    assert res2["done"] is True and res2["examined"] == 7   # continued from 5, not restarted
    assert len(jobs.list_findings(conn, wid)) == 7          # each unique page once


def test_pause_resume_cancel(conn):
    wid = _ws(conn, "ENG_PRC")
    job = jobs.create_job(conn, wid, ACTOR, query="states", depth="quick")
    jobs.claim_next_job(conn, wid, ACTOR)
    assert jobs.pause_job(conn, wid, ACTOR, job["id"])["status"] == "paused"
    assert jobs.resume_job(conn, wid, ACTOR, job["id"])["status"] == "pending"
    assert jobs.cancel_job(conn, wid, ACTOR, job["id"])["status"] == "cancelled"
    # a cancelled job is not claimable
    assert jobs.claim_next_job(conn, wid, ACTOR) is None


def test_image_finding_via_injected_ocr(conn):
    wid = _ws(conn, "ENG_OCR")
    jobs.create_job(conn, wid, ACTOR, query="scanned clipping", depth="quick")
    claimed = jobs.claim_next_job(conn, wid, ACTOR)
    def handler(req): return httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNGfake")
    fetcher = Fetcher(resolver=lambda h: [PUBLIC_IP], transport=httpx.MockTransport(handler),
                      respect_robots=False, allowed_content_types=("image/png",))
    fake_ocr = lambda raw: ("Rhymney 112 all out, Moyston 98. Rhymney won by 14 runs.", 0.7)
    reng.run_step(conn, wid, ACTOR, jobs.get_job(conn, claimed["id"]), settings=settings,
                  page_fetcher=fetcher, discovery=_discovery(["https://example.com/clip.png"]), ocr_engine=fake_ocr)
    findings = jobs.list_findings(conn, wid)
    assert len(findings) == 1 and findings[0]["kind"] in ("scorecard", "result", "match_candidate")


def test_ocr_image_graceful_fallback(monkeypatch):
    from onestats.domain.research import extraction
    monkeypatch.setattr(extraction, "default_engine", lambda: (None, None))
    assert reng._ocr_image(b"x", None) == ""                    # no engine → no text (honest)
    assert reng._ocr_image(b"x", lambda raw: ("hi", 0.5)) == "hi"  # injected engine is used


def _seed_match(conn, wid, home, away, year, *, margin_runs=None):
    org = conn.execute(text("INSERT INTO organisation(workspace_id, name) VALUES (:w, :n) RETURNING id"),
                       {"w": wid, "n": f"{home} org"}).scalar_one()
    def team(n):
        return conn.execute(text("INSERT INTO team(workspace_id, organisation_id, name) VALUES (:w, :o, :n) RETURNING id"),
                            {"w": wid, "o": org, "n": n}).scalar_one()
    hid, aid = team(home), team(away)
    mid = conn.execute(text("INSERT INTO match(workspace_id, match_date, margin_runs) VALUES (:w, :d, :mr) RETURNING id"),
                       {"w": wid, "d": f"{year}-01-14", "mr": margin_runs}).scalar_one()
    for tid, home_flag in ((hid, True), (aid, False)):
        conn.execute(text("INSERT INTO match_team(workspace_id, match_id, team_id, is_home) "
                          "VALUES (:w, :m, :t, :h)"), {"w": wid, "m": mid, "t": tid, "h": home_flag})
    return str(mid)


def test_finding_classified_possible_duplicate_against_existing_match(conn):
    wid = _ws(conn, "ENG_CLASS")
    _seed_match(conn, wid, "Rhymney", "Moyston", 1905)
    jobs.create_job(conn, wid, ACTOR, query="Rhymney 1905", depth="quick")
    claimed = jobs.claim_next_job(conn, wid, ACTOR)
    # SCORECARD text names "Rhymney v Moyston 1905" → should match the seeded 1905 match.
    def handler(req): return _page(SCORECARD)
    reng.run_step(conn, wid, ACTOR, jobs.get_job(conn, claimed["id"]), settings=settings,
                  page_fetcher=_fetcher(handler), discovery=_discovery(["https://example.com/m"]))
    f = jobs.list_findings(conn, wid)[0]
    assert f["classification"] == "possible_duplicate"
    assert (f["extracted"] or {}).get("candidate_match_ids")  # points the reviewer at the existing match


def test_finding_suggests_existing_person_for_named_player(conn):
    wid = _ws(conn, "ENG_IDENT")
    conn.execute(text("INSERT INTO person(workspace_id, display_name) VALUES (:w, 'John Smith')"), {"w": wid})
    jobs.create_job(conn, wid, ACTOR, query="players", depth="quick")
    claimed = jobs.claim_next_job(conn, wid, ACTOR)
    def handler(req): return _page(SCORECARD)  # scorecard names "J Smith ..."
    reng.run_step(conn, wid, ACTOR, jobs.get_job(conn, claimed["id"]), settings=settings,
                  page_fetcher=_fetcher(handler), discovery=_discovery(["https://example.com/m"]))
    f = jobs.list_findings(conn, wid)[0]
    sugg = (f["extracted"] or {}).get("player_suggestions") or {}
    assert any(k.lower().endswith("smith") for k in sugg)  # J Smith → John Smith suggested, not merged
    assert f["status"] == "pending_review"


def test_finding_flagged_conflicting_when_result_differs(conn):
    wid = _ws(conn, "ENG_CONFLICT")
    _seed_match(conn, wid, "Rhymney", "Moyston", 1905, margin_runs=20)  # record says 20 runs
    jobs.create_job(conn, wid, ACTOR, query="result conflict", depth="quick")
    claimed = jobs.claim_next_job(conn, wid, ACTOR)
    def handler(req): return _page(SCORECARD)  # SCORECARD says "won by 14 runs"
    reng.run_step(conn, wid, ACTOR, jobs.get_job(conn, claimed["id"]), settings=settings,
                  page_fetcher=_fetcher(handler), discovery=_discovery(["https://example.com/m"]))
    f = jobs.list_findings(conn, wid)[0]
    assert f["classification"] == "conflicting"
    assert f["status"] == "pending_review"   # never auto-applied; the verified record is untouched


def test_deep_depth_runs_without_js_render(conn, monkeypatch):
    monkeypatch.delenv("ONESTATS_RESEARCH_JS", raising=False)  # JS rendering stays off
    wid = _ws(conn, "ENG_DEEP")
    jobs.create_job(conn, wid, ACTOR, query="deep run", depth="deep")
    claimed = jobs.claim_next_job(conn, wid, ACTOR)
    def handler(req): return _page(SCORECARD)
    res = reng.run_step(conn, wid, ACTOR, jobs.get_job(conn, claimed["id"]), settings=settings,
                        page_fetcher=_fetcher(handler), discovery=_discovery(["https://example.com/m"]))
    assert res["done"] is True
    assert len(jobs.list_findings(conn, wid)) == 1


def test_depth_breadth_ordering():
    assert reng.DEPTH_PER_QUERY["quick"] < reng.DEPTH_PER_QUERY["standard"] < reng.DEPTH_PER_QUERY["deep"]


def test_allowed_sources_restricts_retrieval(conn):
    wid = _ws(conn, "ENG_ALLOW")
    # job restricted to example.com; discovery also offers an off-list host
    jobs.create_job(conn, wid, ACTOR, query="policy", depth="quick",
                          context={"allowed_sources": ["example.com"]})
    claimed = jobs.claim_next_job(conn, wid, ACTOR)
    def handler(req): return _page(SCORECARD)
    reng.run_step(conn, wid, ACTOR, jobs.get_job(conn, claimed["id"]), settings=settings,
                  page_fetcher=_fetcher(handler),
                  discovery=_discovery(["https://example.com/ok", "https://benchmark.test/off"]))
    outcomes = {r[0]: r[1] for r in conn.execute(text(
        "SELECT url, outcome FROM research_fetch WHERE job_id = :j"), {"j": claimed["id"]}).all()}
    assert outcomes["https://example.com/ok"] == "fetched"
    assert outcomes["https://benchmark.test/off"] == "blocked"   # off the allow-list → never fetched
    # the only finding came from the allowed host
    assert all(f["source_host"] == "example.com" for f in jobs.list_findings(conn, wid))


def test_workspace_isolation_of_findings(conn):
    a = _ws(conn, "ENG_WS_A")
    jobs.create_job(conn, a, ACTOR, query="iso", depth="quick")
    claimed = jobs.claim_next_job(conn, a, ACTOR)
    def handler(req): return _page(SCORECARD)
    reng.run_step(conn, a, ACTOR, jobs.get_job(conn, claimed["id"]), settings=settings,
                  page_fetcher=_fetcher(handler), discovery=_discovery(["https://example.com/x"]))
    assert len(jobs.list_findings(conn, a)) == 1
    # switch RLS context to a different workspace — the findings must be invisible
    b = _ws(conn, "ENG_WS_B")
    assert jobs.list_findings(conn, b) == []
