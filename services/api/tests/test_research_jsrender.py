"""Optional JS rendering — default-off and graceful. No browser is launched in these tests."""
from __future__ import annotations

from onestats.domain.research import jsrender


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ONESTATS_RESEARCH_JS", raising=False)
    assert jsrender.enabled() is False
    assert jsrender.render("https://example.com/x") is None  # disabled → None, never raises


def test_enabled_but_playwright_absent_is_graceful(monkeypatch):
    monkeypatch.setenv("ONESTATS_RESEARCH_JS", "1")
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "playwright" or name.startswith("playwright."):
            raise ImportError("no playwright")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    assert jsrender.enabled() is False                        # import fails → unavailable
    assert jsrender.render("https://example.com/x") is None


def test_render_refuses_non_public_target(monkeypatch):
    # Even enabled, a non-public host is screened out before any browser launch.
    monkeypatch.setenv("ONESTATS_RESEARCH_JS", "1")
    assert jsrender.render("http://127.0.0.1/admin", resolver=lambda h: ["127.0.0.1"]) is None
