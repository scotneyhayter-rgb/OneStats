"""Catalogue wiring regressions that need no database — they assert how reports are configured.

The Most Run Outs report (and the shared fielding RO column) must credit run-out *involvements*
(direct run outs + recorded assists), matching the player profile and the records-page ranking.
Ranking/showing bare primary run_outs under-credited fielders who were often the assisting fielder.
"""
from __future__ import annotations

from onestats.reports import catalogue


def _entry(entry_id: str) -> catalogue.CatEntry:
    return next(e for e in catalogue.CATALOGUE if e.id == entry_id)


def test_most_run_outs_ranks_by_involvements():
    assert _entry("field_most_run_outs").params["order_by"] == "run_out_involvements"


def test_fielding_ro_column_shows_involvements():
    keys = [c.key for c in catalogue.REPORTS["fielding"]["columns"]]
    assert "run_out_involvements" in keys          # RO column credits involvements
    assert "run_outs" not in keys                  # not the bare primary-only count
    ro = next(c for c in catalogue.REPORTS["fielding"]["columns"] if c.key == "run_out_involvements")
    assert ro.label == "RO"
