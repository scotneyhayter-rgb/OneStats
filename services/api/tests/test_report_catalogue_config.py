"""Catalogue wiring regressions that need no database — they assert how reports are configured.

The Most Run Outs report (and the shared fielding RO column) must credit run-out *involvements*
(direct run outs + recorded assists), matching the player profile and the records-page ranking.
Ranking/showing bare primary run_outs under-credited fielders who were often the assisting fielder.
"""
from __future__ import annotations

from onestats.domain.stats import rankings
from onestats.reports import catalogue


def _entry(entry_id: str) -> catalogue.CatEntry:
    return next(e for e in catalogue.CATALOGUE if e.id == entry_id)


# ---- player rankings: component maths, config invariants and catalogue wiring (no DB needed) ----
def test_ranking_component_scoring_and_clamp():
    assert rankings._direct(25, 50) == 50          # higher-is-better: value/bench
    assert rankings._direct(100, 50) == 100        # clamped to 100
    assert rankings._direct(None, 50) == 0         # missing value guarded
    assert rankings._inverse(40, 20) == 50         # lower-is-better: bench/value
    assert rankings._inverse(10, 20) == 100        # clamped to 100
    assert rankings._inverse(0, 20) == 0           # divide-by-zero guarded
    assert rankings._inverse(None, 20) == 0        # undefined (e.g. 0 wickets) guarded


def test_ranking_weights_sum_to_one():
    for discipline, w in rankings.WEIGHTS.items():
        assert round(sum(w.values()), 6) == 1.0, discipline


def test_ranking_benchmarks_cover_both_format_families():
    for family in ("long", "short"):
        b = rankings.BENCHMARKS[family]
        for key in ("bat_avg", "rpm", "bat_sr", "milestone", "bowl_avg", "wpm", "econ", "bowl_sr"):
            assert b[key] > 0, (family, key)


def test_rankings_reports_registered():
    ids = {e.id for e in catalogue.CATALOGUE}
    assert {"rank_batting", "rank_bowling", "rank_allrounder"} <= ids
    assert "Rankings" in catalogue.CATEGORY_ORDER
    for base in ("rankings_batting", "rankings_bowling", "rankings_allrounder"):
        assert base in catalogue.REPORTS


def test_most_run_outs_ranks_by_involvements():
    assert _entry("field_most_run_outs").params["order_by"] == "run_out_involvements"


def test_fielding_ro_column_shows_involvements():
    keys = [c.key for c in catalogue.REPORTS["fielding"]["columns"]]
    assert "run_out_involvements" in keys          # RO column credits involvements
    assert "run_outs" not in keys                  # not the bare primary-only count
    ro = next(c for c in catalogue.REPORTS["fielding"]["columns"] if c.key == "run_out_involvements")
    assert ro.label == "RO"
