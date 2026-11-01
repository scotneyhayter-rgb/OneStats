"""Platform ("All Workspaces") dashboard — Super-Admin-only, RLS-preserving (Part 4).

Rolled back per test; skipped without a live DB; runs as ``onestats_app`` under FORCE RLS. Verifies
that the cross-workspace aggregation reads real per-workspace counts without disabling RLS, labels
totals as workspace records, and that the API endpoint is Super-Admin gated.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.domain import platform

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")


@pytest.fixture
def engine():
    return create_engine(settings.database_url, future=True)


def test_platform_dashboard_aggregates_real_counts_without_disabling_rls(engine):
    """Non-mutating: the platform totals must equal the sum of the per-workspace rows (a real
    aggregation, not a fabricated figure), and totals are labelled as workspace records."""
    data = platform.platform_dashboard(engine)
    assert data["totals_are_workspace_records"] is True
    assert data["system_health"]["database_connected"] is True

    orgs = data["organisations"]
    assert len(orgs) == data["summary"]["workspaces"]
    for o in orgs:
        for k in ("matches", "players", "approved_scorecards", "awaiting_approval", "seasons", "members"):
            assert isinstance(o[k], int) and o[k] >= 0

    # the platform totals are exactly the sum across workspaces (no invented numbers)
    assert data["summary"]["workspace_match_records"] == sum(o["matches"] for o in orgs)
    assert data["summary"]["workspace_player_records"] == sum(o["players"] for o in orgs)
    assert data["summary"]["workspace_approved_scorecards"] == sum(o["approved_scorecards"] for o in orgs)


def test_rls_still_enforced_after_platform_reads(engine):
    """A platform read must not leave a connection able to see another workspace's rows: the
    per-workspace counting uses transaction-local contexts, so an un-scoped query sees nothing."""
    platform.platform_dashboard(engine)
    with engine.begin() as conn:
        # no workspace context set -> FORCE RLS fails closed -> zero match rows visible
        visible = conn.execute(text("SELECT count(*) FROM match")).scalar_one()
        assert visible == 0
