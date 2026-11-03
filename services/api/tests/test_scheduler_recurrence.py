"""Timezone-aware weekly recurrence (DST-safe) — pure-function tests, no database.

These lock down the behaviour the International workspace's Saturday 04:00 Australia/Melbourne update
relies on: the local wall-clock time is preserved across daylight-saving transitions (so the UTC
instant shifts by the offset change rather than the local time drifting), and the catch-up / due
helpers behave as the worker expects.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from onestats.domain.scheduler import recurrence

MEL = "Australia/Melbourne"
UTC = dt.timezone.utc


def _occ(after: dt.datetime) -> dt.datetime:
    return recurrence.next_weekly_occurrence(after, day_of_week=5, hour=4, minute=0, tz=MEL)


def test_next_occurrence_is_saturday_0400_local_and_utc_aware():
    result = _occ(dt.datetime(2026, 7, 6, 0, 0, tzinfo=UTC))  # a Monday in winter
    assert result.tzinfo is UTC or result.utcoffset() == dt.timedelta(0)
    local = result.astimezone(ZoneInfo(MEL))
    assert local.weekday() == 5 and local.hour == 4 and local.minute == 0
    assert result > dt.datetime(2026, 7, 6, 0, 0, tzinfo=UTC)


def test_dst_summer_saturday_0400_is_1700_utc_friday():
    # During AEDT (+11), 04:00 Sat local == 17:00 Fri UTC.
    result = _occ(dt.datetime(2026, 3, 23, 0, 0, tzinfo=UTC))  # week of Sat 2026-03-28
    assert result == dt.datetime(2026, 3, 27, 17, 0, tzinfo=UTC)


def test_standard_time_saturday_0400_is_1800_utc_friday():
    # During AEST (+10), 04:00 Sat local == 18:00 Fri UTC — one hour later in UTC than in summer.
    result = _occ(dt.datetime(2026, 7, 6, 0, 0, tzinfo=UTC))  # week of Sat 2026-07-11
    assert result == dt.datetime(2026, 7, 10, 18, 0, tzinfo=UTC)


def test_weekly_step_crosses_fall_back_without_drifting_local_time():
    # Stepping week to week across the 2026-04-05 fall-back keeps 04:00 LOCAL each Saturday even though
    # the UTC instant changes from 17:00 to 18:00. Naive +7 days arithmetic would drift the local time.
    before = _occ(dt.datetime(2026, 3, 23, 0, 0, tzinfo=UTC))   # 2026-03-28 (AEDT) -> 17:00Z
    # the first Saturday AFTER the 2026-04-05 fall-back (asked from Mon 2026-04-06)
    after = _occ(dt.datetime(2026, 4, 6, 0, 0, tzinfo=UTC))
    assert before == dt.datetime(2026, 3, 27, 17, 0, tzinfo=UTC)
    assert after == dt.datetime(2026, 4, 10, 18, 0, tzinfo=UTC)
    for inst in (before, after):
        local = inst.astimezone(ZoneInfo(MEL))
        assert (local.weekday(), local.hour, local.minute) == (5, 4, 0)


def test_spring_forward_week_still_lands_0400_local():
    # Week of the 2026-10-04 spring-forward (02:00->03:00). 04:00 Saturday is above the gap, so it
    # resolves cleanly; the following Saturday 2026-10-10 is AEDT (+11) -> 17:00Z.
    result = _occ(dt.datetime(2026, 10, 5, 0, 0, tzinfo=UTC))
    assert result == dt.datetime(2026, 10, 9, 17, 0, tzinfo=UTC)
    local = result.astimezone(ZoneInfo(MEL))
    assert (local.weekday(), local.hour, local.minute) == (5, 4, 0)


def test_same_weekday_before_time_returns_today_not_next_week():
    # Friday->Saturday boundary: asked on Saturday before 04:00 local, the due time is TODAY 04:00.
    sat_0200_local = dt.datetime(2026, 7, 11, 2, 0, tzinfo=ZoneInfo(MEL)).astimezone(UTC)
    result = _occ(sat_0200_local)
    assert result == dt.datetime(2026, 7, 10, 18, 0, tzinfo=UTC)  # 2026-07-11 04:00 AEST


def test_same_weekday_after_time_returns_next_week():
    sat_0500_local = dt.datetime(2026, 7, 11, 5, 0, tzinfo=ZoneInfo(MEL)).astimezone(UTC)
    result = _occ(sat_0500_local)
    local = result.astimezone(ZoneInfo(MEL))
    assert local.date() == dt.date(2026, 7, 18) and local.hour == 4


def test_is_catch_up_and_is_due():
    sched = dt.datetime(2026, 7, 10, 18, 0, tzinfo=UTC)
    assert recurrence.is_catch_up(sched, sched + dt.timedelta(hours=5)) is True
    assert recurrence.is_catch_up(sched, sched + dt.timedelta(seconds=30)) is False
    assert recurrence.is_catch_up(None, sched) is False
    assert recurrence.is_due(sched, sched + dt.timedelta(seconds=1)) is True
    assert recurrence.is_due(sched, sched - dt.timedelta(seconds=1)) is False
    assert recurrence.is_due(None, sched) is False
