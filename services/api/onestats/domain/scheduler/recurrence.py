"""Timezone-aware weekly recurrence (DST-safe). Pure functions — no database, no clock reads except
those passed in — so the daylight-saving and catch-up behaviour is directly unit-testable.

All instants crossing in and out are timezone-aware ``datetime``s. Internally the next occurrence is
computed in the task's IANA zone (via :class:`zoneinfo.ZoneInfo`) and converted back to UTC, so a
weekly task does NOT drift by an hour across a daylight-saving boundary the way naive 7-day arithmetic
would.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

# A run that starts more than this many seconds after its scheduled instant is a late "catch-up"
# (e.g. the PC was powered off at the scheduled time and the task fired on next startup).
CATCH_UP_TOLERANCE_SECONDS = 120


def _require_aware(value: dt.datetime, name: str) -> dt.datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def next_weekly_occurrence(
    after: dt.datetime, *, day_of_week: int, hour: int, minute: int, tz: str
) -> dt.datetime:
    """The first occurrence of (``day_of_week`` at ``hour``:``minute`` local to ``tz``) that is
    STRICTLY after ``after``, returned as a UTC-aware datetime.

    ``day_of_week`` follows Python's convention: Monday=0 .. Sunday=6 (so Saturday=5).

    DST handling: the local wall-clock target (e.g. 04:00 Saturday) is attached to the zone and
    converted to UTC, so the returned instant tracks the zone's offset on that date. 04:00 is chosen
    for the International workspace precisely because it never falls in Melbourne's DST gap (the
    transitions occur around 02:00–03:00 on Sundays), but the computation is general: if a target wall
    time happens to be skipped or repeated by a transition, ``zoneinfo`` resolves it deterministically
    (``fold`` semantics) rather than raising.
    """
    _require_aware(after, "after")
    zone = ZoneInfo(tz)
    local_after = after.astimezone(zone)

    days_ahead = (day_of_week - local_after.weekday()) % 7
    target_date = (local_after + dt.timedelta(days=days_ahead)).date()
    local_dt = dt.datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=zone)

    # If that instant is not strictly in the future (same weekday but the time already passed, or
    # exactly equal), step to the following week.
    if local_dt.astimezone(dt.timezone.utc) <= after.astimezone(dt.timezone.utc):
        target_date = target_date + dt.timedelta(days=7)
        local_dt = dt.datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=zone)

    return local_dt.astimezone(dt.timezone.utc)


def is_catch_up(scheduled_for: dt.datetime | None, ran_at: dt.datetime,
                tolerance_seconds: int = CATCH_UP_TOLERANCE_SECONDS) -> bool:
    """True when a run that satisfies ``scheduled_for`` actually started late enough to count as a
    missed-then-caught-up occurrence rather than an on-time run."""
    if scheduled_for is None:
        return False
    _require_aware(scheduled_for, "scheduled_for")
    _require_aware(ran_at, "ran_at")
    return (ran_at - scheduled_for).total_seconds() > tolerance_seconds


def is_due(next_run_at: dt.datetime | None, now: dt.datetime) -> bool:
    """Whether a task whose next occurrence is ``next_run_at`` is due at ``now`` (past-due included —
    that is how a missed occurrence becomes a catch-up)."""
    if next_run_at is None:
        return False
    _require_aware(next_run_at, "next_run_at")
    _require_aware(now, "now")
    return next_run_at <= now
