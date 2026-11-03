"""Worker tick coexistence + failure isolation: a failing scheduler/cricsheet tick must never raise
into the research loop, and one failing tick must not stop the others."""
from __future__ import annotations

import sys
import types

from onestats.domain.research.worker import ResearchWorker


def _worker():
    return ResearchWorker(engine=object(), settings=object())  # ticks are patched; engine unused here


def _install(monkeypatch, modpath: str, attr: str, fn):
    mod = types.ModuleType(modpath)
    setattr(mod, attr, fn)
    # ensure parent package import works (onestats.domain.scheduler / onestats.domain.intl exist already)
    monkeypatch.setitem(sys.modules, modpath, mod)


def test_scheduler_tick_swallows_failure(monkeypatch):
    def boom(_engine, **k):
        raise RuntimeError("scheduler exploded")
    _install(monkeypatch, "onestats.domain.scheduler.worker", "tick_all_workspaces", boom)
    _worker()._scheduler_tick()  # must not raise


def test_cricsheet_tick_swallows_failure(monkeypatch):
    def boom(_engine, **k):
        raise RuntimeError("cricsheet exploded")
    _install(monkeypatch, "onestats.domain.intl.cricsheet_worker", "run_due", boom)
    _worker()._cricsheet_tick()  # must not raise


def test_one_failing_tick_does_not_stop_the_other(monkeypatch):
    calls = {"cricsheet": 0}
    def sched_boom(_engine, **k):
        raise RuntimeError("scheduler down")
    def cricsheet_ok(_engine, **k):
        calls["cricsheet"] += 1
        return {"ticked": 0}
    _install(monkeypatch, "onestats.domain.scheduler.worker", "tick_all_workspaces", sched_boom)
    _install(monkeypatch, "onestats.domain.intl.cricsheet_worker", "run_due", cricsheet_ok)
    w = _worker()
    # Mirror the loop's end-of-iteration sequence: scheduler then cricsheet, each isolated.
    w._scheduler_tick()
    w._cricsheet_tick()
    assert calls["cricsheet"] == 1  # the cricsheet tick still ran despite the scheduler failing
