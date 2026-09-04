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


def _normal_due_after(anchor: datetime, monitor: Mapping[str, Any]) -> datetime:
    """Find the first minute due under the cadence active at that instant."""

    previous = parse_instant(anchor, str(monitor.get("timezone", "America/Los_Angeles")))
    for minute in range(1, 24 * 60 + 1):
        candidate = previous + timedelta(minutes=minute)
        if candidate - previous >= timedelta(minutes=cadence_minutes(candidate, monitor)):
            return candidate
    return previous + timedelta(minutes=cadence_minutes(previous, monitor))


def source_failure_next_due_at(
    last_attempt_at: str | datetime,
    monitor: Mapping[str, Any],
    *,
    error_code: str | None,
    consecutive_failures: int,
) -> str:
    """Return the retry time for a failed source attempt.

    Access denials receive a long fixed cooldown. Other failures retain at
    least the normal local-time cadence and back off across consecutive
    failures so a stale successful snapshot does not cause every scheduler
    wake-up to hit the source.
    """

    timezone_name = str(monitor.get("timezone", "America/Los_Angeles"))
    attempted = parse_instant(last_attempt_at, timezone_name)
    normal_due = _normal_due_after(attempted, monitor)
    source = monitor.get("source", {})
    normalized_code = str(error_code or "source_error").casefold()
    if normalized_code == "http_403":
        configured_hours = max(0.0, float(source.get("http_403_cooldown_hours", 6)))
        due = max(normal_due, attempted + timedelta(hours=configured_hours))
    else:
        cap = max(1, int(source.get("transient_failure_backoff_multiplier_cap", 4)))
        failures = max(1, int(consecutive_failures))
        exponent = min(failures - 1, cap.bit_length())
        multiplier = min(2**exponent, cap)
        due = attempted + (normal_due - attempted) * multiplier
    return utc_iso(due)


def is_due(
    now: datetime,
    last_successful_at: str | datetime | None,
    monitor: Mapping[str, Any],
    *,
    force: bool = False,
    last_attempt_at: str | datetime | None = None,
    last_error_code: str | None = None,
    consecutive_failures: int = 0,
) -> bool:
    if force:
        return True
    timezone_name = str(monitor.get("timezone", "America/Los_Angeles"))
    current = parse_instant(now, timezone_name)
    if last_attempt_at is not None and int(consecutive_failures or 0) > 0:
        retry_at = parse_instant(
            source_failure_next_due_at(
                last_attempt_at,
                monitor,
                error_code=last_error_code,
                consecutive_failures=consecutive_failures,
            ),
            timezone_name,
        )
        return current >= retry_at
    if last_successful_at is None:
        return True
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
    return utc_iso(_normal_due_after(previous, monitor))
