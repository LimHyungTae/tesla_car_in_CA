"""Atomic JSON persistence and dashboard synchronization."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class StorageError(RuntimeError):
    """A canonical JSON file exists but cannot be read safely."""


def read_json(path: Path, default: Any, *, strict: bool = False) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        if strict:
            raise StorageError(f"Could not read canonical JSON {path}: {exc}") from exc
        return default


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _inventory_count(document: Any) -> int:
    if isinstance(document, dict):
        if isinstance(document.get("count"), int):
            return int(document["count"])
        if isinstance(document.get("vehicles"), list):
            return len(document["vehicles"])
    if isinstance(document, list):
        return len(document)
    return 0


def public_status_document(state: Any, inventory: Any) -> dict[str, Any]:
    """Build the stable public status contract consumed by the dashboard."""

    internal = state if isinstance(state, dict) else {}
    candidate_count = _inventory_count(inventory)
    last_successful = internal.get("last_successful_at")
    stale = bool(internal.get("stale", last_successful is None))
    source_failed = internal.get("last_status") == "source_error"
    has_baseline = bool(last_successful) and candidate_count > 0
    if source_failed or stale:
        public_status = "degraded" if has_baseline else "failed"
    else:
        public_status = "healthy"
    failure_reason = internal.get("last_error") if public_status != "healthy" else None
    if public_status != "healthy" and not failure_reason:
        failure_reason = (
            "The last successful inventory baseline is stale"
            if has_baseline
            else "No successful inventory baseline is available"
        )
    return {
        "schema_version": 1,
        "status": public_status,
        "failure_reason": failure_reason,
        "last_successful_crawl": last_successful,
        "last_attempted_crawl": internal.get("last_attempt_at"),
        "stale": stale,
        "current_candidates": candidate_count,
        "last_internal_status": internal.get("last_status"),
        "last_run_at": internal.get("last_run_at"),
        "next_due_at": internal.get("next_due_at"),
        "consecutive_failures": int(internal.get("consecutive_failures", 0) or 0),
        "last_event_count": int(internal.get("last_event_count", 0) or 0),
        "last_alert_count": int(internal.get("last_alert_count", 0) or 0),
    }


def sync_dashboard(paths: dict[str, Path]) -> None:
    inventory = read_json(paths["inventory"], {})
    state = read_json(paths["state"], {})
    if paths["inventory"].exists():
        atomic_write_json(paths["dashboard_inventory"], inventory)
    if paths["history"].exists():
        atomic_write_json(paths["dashboard_history"], read_json(paths["history"], {}))
    if paths["state"].exists():
        atomic_write_json(
            paths["dashboard_status"],
            public_status_document(state, inventory),
        )
    for source_key, destination_key in (
        ("buy_box_config", "dashboard_buy_box_config"),
        ("monitor_config", "dashboard_monitor_config"),
    ):
        if paths[source_key].exists():
            atomic_write_json(paths[destination_key], read_json(paths[source_key], {}))
