"""Timezone-aware recurrence (DST-safe). Pure functions — no database, no clock reads except those
passed in — so the daylight-saving and catch-up behaviour is directly unit-testable.

All instants crossing in and out are timezone-aware ``datetime``s. Internally the next occurrence is
computed in the task's IANA zone (via :class:`zoneinfo.ZoneInfo`) and converted back to UTC, so a daily
or weekly task does NOT drift by an hour across a daylight-saving boundary the way naive day-count
arithmetic would.
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
    if local_dt.astimezone(dt.UTC) <= after.astimezone(dt.UTC):
        target_date = target_date + dt.timedelta(days=7)
        local_dt = dt.datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=zone)

    return local_dt.astimezone(dt.UTC)


def next_daily_occurrence(after: dt.datetime, *, hour: int, minute: int, tz: str) -> dt.datetime:
    """The first occurrence of (``hour``:``minute`` local to ``tz``, every day) that is STRICTLY after
    ``after``, returned as a UTC-aware datetime.

    DST handling matches :func:`next_weekly_occurrence`: the local wall-clock target is attached to the
    zone and converted to UTC, so 04:00 local stays 04:00 local on every date and the UTC instant tracks
    the zone's offset. (For Melbourne, 04:00 is outside the ~02:00–03:00 DST transition window, so it is
    never skipped or repeated; a target that did fall in a gap would be resolved deterministically by
    ``zoneinfo`` rather than raising.)
    """
    _require_aware(after, "after")
    zone = ZoneInfo(tz)
    local_after = after.astimezone(zone)

    target_date = local_after.date()
    local_dt = dt.datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=zone)
    # Not strictly in the future (time already passed today, or exactly equal) -> tomorrow.
    if local_dt.astimezone(dt.UTC) <= after.astimezone(dt.UTC):
        target_date = target_date + dt.timedelta(days=1)
        local_dt = dt.datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=zone)

    return local_dt.astimezone(dt.UTC)


def next_occurrence(after: dt.datetime, *, schedule_kind: str, hour: int, minute: int, tz: str,
                    day_of_week: int | None = None) -> dt.datetime:
    """Dispatch to the recurrence family for ``schedule_kind`` (``daily`` or ``weekly``). Weekly
    requires ``day_of_week`` (Monday=0 .. Sunday=6); daily ignores it."""
    if schedule_kind == "daily":
        return next_daily_occurrence(after, hour=hour, minute=minute, tz=tz)
    if schedule_kind == "weekly":
        if day_of_week is None:
            raise ValueError("weekly schedule requires day_of_week")
        return next_weekly_occurrence(after, day_of_week=day_of_week, hour=hour, minute=minute, tz=tz)
    raise ValueError(f"unknown schedule_kind {schedule_kind!r}")


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
