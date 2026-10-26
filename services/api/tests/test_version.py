"""Version parsing + client/server compatibility rules (pure, no DB)."""

from __future__ import annotations

from onestats.core import version as ver


def test_parse_and_compare_semver():
    assert ver.parse_version("1.2.0") is not None
    assert ver.compare_versions("1.2.0", "1.1.0") == 1
    assert ver.compare_versions("1.1.0", "1.2.0") == -1
    assert ver.compare_versions("1.2.0", "1.2.0") == 0


def test_prerelease_ranks_below_final():
    # A final release outranks a prerelease of the same x.y.z (semver §11).
    assert ver.compare_versions("1.0.0", "1.0.0-beta.1") == 1
    assert ver.compare_versions("1.0.0-beta.1", "1.0.0-beta.2") == -1


def test_unparseable_sorts_low_and_is_tolerated():
    assert ver.parse_version("not-a-version") is None
    assert ver.compare_versions("garbage", "1.0.0") == -1


def test_compatibility_ok_for_current_desktop():
    r = ver.evaluate_compatibility(ver.MIN_DESKTOP_VERSION)
    assert r["status"] == "ok"
    assert r["can_operate"] is True


def test_compatibility_rejects_too_old_desktop():
    r = ver.evaluate_compatibility("0.9.0")
    assert r["status"] == "desktop_too_old"
    assert r["can_operate"] is False
    assert r["required_action"] == "update_desktop"


def test_compatibility_maintenance_blocks():
    r = ver.evaluate_compatibility(ver.MIN_DESKTOP_VERSION, maintenance=True)
    assert r["status"] == "maintenance"
    assert r["can_operate"] is False


def test_compatibility_unknown_version_proceeds():
    r = ver.evaluate_compatibility(None)
    assert r["status"] == "unknown"
    assert r["can_operate"] is True
