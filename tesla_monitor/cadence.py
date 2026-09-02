"""Timezone-correct scheduling helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo


UTC = timezone.utc


def parse_instant(value: str | datetime | None, timezone_name: str = "America/Los_Angeles") -> datetime:
    """Return an aware UTC datetime.

    CLI timestamps without an offset are intentionally interpreted in the
    configured local timezone. This makes ``--now 2026-09-02T00:10:00`` useful
    while preserving unambiguous UTC persistence.
    """

    if value is None:
        parsed = datetime.now(UTC)
    elif isinstance(value, datetime):
        parsed = value
    else:
        text = value.strip()
        if text.endswith(("Z", "z")):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed.astimezone(UTC)


def utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def cadence_minutes(now: datetime, monitor: Mapping[str, Any]) -> int:
    timezone_name = str(monitor.get("timezone", "America/Los_Angeles"))
    local = parse_instant(now, timezone_name).astimezone(ZoneInfo(timezone_name))
    cadence = monitor.get("cadence", {})
    start = int(
        cadence.get(
            "overnight_start_hour",
            cadence.get("night_start_hour", cadence.get("night_start", 0)),
        )
    )
    end = int(
        cadence.get(
            "overnight_end_hour_exclusive",
            cadence.get("night_end_hour_exclusive", cadence.get("night_end_exclusive", 5)),
        )
    )
    night_minutes = int(cadence.get("overnight_interval_minutes", cadence.get("night_minutes", 15)))
    day_minutes = int(cadence.get("day_interval_minutes", cadence.get("day_minutes", 30)))
    if start <= local.hour < end:
        return night_minutes
    return day_minutes


def is_due(
    now: datetime,
    last_successful_at: str | datetime | None,
    monitor: Mapping[str, Any],
    *,
    force: bool = False,
) -> bool:
    if force or last_successful_at is None:
        return True
    timezone_name = str(monitor.get("timezone", "America/Los_Angeles"))
    current = parse_instant(now, timezone_name)
    previous = parse_instant(last_successful_at, timezone_name)
    elapsed = current - previous
    if elapsed < timedelta(0):
        return False
    return elapsed >= timedelta(minutes=cadence_minutes(current, monitor))


def is_stale(
    now: datetime,
    last_successful_at: str | datetime | None,
    monitor: Mapping[str, Any],
) -> bool:
    if last_successful_at is None:
        return True
    timezone_name = str(monitor.get("timezone", "America/Los_Angeles"))
    current = parse_instant(now, timezone_name)
    previous = parse_instant(last_successful_at, timezone_name)
    if previous > current:
        return True
    multiplier = float(monitor.get("cadence", {}).get("stale_multiplier", 2))
    threshold = timedelta(minutes=cadence_minutes(current, monitor) * multiplier)
    return current - previous > threshold


def next_due_at(now: datetime, last_successful_at: str | datetime | None, monitor: Mapping[str, Any]) -> str:
    current = parse_instant(now, str(monitor.get("timezone", "America/Los_Angeles")))
    if last_successful_at is None:
        return utc_iso(current)
    previous = parse_instant(last_successful_at, str(monitor.get("timezone", "America/Los_Angeles")))
    # The interval can change at 00:00 and 05:00 local time. Find the first
    # real-time minute that is due under the cadence active at that instant.
    for minute in range(1, 121):
        candidate = previous + timedelta(minutes=minute)
        if candidate - previous >= timedelta(minutes=cadence_minutes(candidate, monitor)):
            return utc_iso(candidate)
    return utc_iso(previous + timedelta(minutes=cadence_minutes(current, monitor)))
