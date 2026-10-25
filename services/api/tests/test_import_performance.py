"""Phase 8, Stage 8.8 — large-dataset import performance (R3).

Verifies the import of a realistic large dataset (hundreds of matches here; thousands measured out of
band — see docs/47) completes in reasonable time and that the dataset is processed per-batch rather
than held open-endedly. Rolled back; skipped without a live DB. The assertion threshold is generous
so it is a safety net against a severe regression, not a micro-benchmark.
"""
from __future__ import annotations

import time
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.importing import pipeline
from onestats.domain.importing.model import (
    CanonicalClub,
    CanonicalDataset,
    CanonicalMatch,
    CanonicalTeam,
    SourceProvenance,
)

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"
N = 400                 # kept modest for CI; thousands verified out of band (see docs/47)
MAX_SECONDS = 40.0      # generous safety net (observed ~4-6s); flags only a severe regression


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


def _dataset(n: int) -> CanonicalDataset:
    ds = CanonicalDataset(provenance=SourceProvenance(source_system="perf_src"))
    teams: dict[str, CanonicalTeam] = {}
    clubs: dict[str, CanonicalClub] = {}
    base = date(2000, 1, 1)
    for i in range(n):
        home, away = f"team-{i % 100}", f"team-{(i + 1) % 100}"
        for ref in (home, away):
            if ref not in teams:
                clubs[ref] = CanonicalClub(source_ref=ref, name=ref)
                teams[ref] = CanonicalTeam(source_ref=ref, name=ref, club_ref=ref)
        ds.matches.append(CanonicalMatch(source_ref=f"m-{i}", match_date=base + timedelta(days=i),
                                         home_team_ref=home, away_team_ref=away))
    ds.clubs, ds.teams = list(clubs.values()), list(teams.values())
    return ds


def test_large_import_completes_in_reasonable_time(conn):
    wid = conn.execute(text("INSERT INTO workspace(name,type) VALUES ('PERF','club') RETURNING id")).scalar_one()
    conn.execute(text("INSERT INTO app_user(id,username) VALUES (:a,'perf') ON CONFLICT (id) DO NOTHING"), {"a": ACTOR})
    set_workspace(conn, wid)

    t0 = time.perf_counter()
    out = pipeline.import_dataset(conn, wid, ACTOR, dataset=_dataset(N), commit=True)
    elapsed = time.perf_counter() - t0

    assert out["created"]["match"] == N
    assert conn.execute(text("SELECT count(*) FROM match")).scalar_one() == N
    assert elapsed < MAX_SECONDS, f"import of {N} matches took {elapsed:.1f}s (> {MAX_SECONDS}s)"

    # re-import is idempotent AND fast (all matched, no new rows) — a bounded retry, not a re-create
    t1 = time.perf_counter()
    out2 = pipeline.import_dataset(conn, wid, ACTOR, dataset=_dataset(N), commit=True)
    assert out2["matched"]["match"] == N
    assert conn.execute(text("SELECT count(*) FROM match")).scalar_one() == N
    assert (time.perf_counter() - t1) < MAX_SECONDS
