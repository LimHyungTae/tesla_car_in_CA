"""Atomic JSON persistence and dashboard synchronization."""

from __future__ import annotations

import json
import os
import re
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


def _inventory_timestamp(document: Any, fallback: Any = None) -> Any:
    if not isinstance(document, dict):
        return fallback
    source = document.get("source")
    source_document = source if isinstance(source, dict) else {}
    return (
        document.get("source_successful_at")
        or document.get("generated_at")
        or document.get("snapshot_at")
        or source_document.get("source_feed_last_seen_at")
        or fallback
    )


def _failure_metadata(
    error: Any,
    *,
    error_code: Any = None,
    http_status: Any = None,
) -> tuple[str | None, int | None]:
    typed_code = str(error_code).strip() if error_code else None
    try:
        typed_http_status = int(http_status) if http_status is not None else None
    except (TypeError, ValueError):
        typed_http_status = None
    if typed_code:
        return typed_code, typed_http_status
    if typed_http_status is not None:
        return f"http_{typed_http_status}", typed_http_status

    text = str(error or "")
    match = re.search(r"\bHTTP(?:\s+Error)?\s+(\d{3})\b", text, flags=re.IGNORECASE)
    legacy_http_status = int(match.group(1)) if match else None
    if legacy_http_status is not None:
        return f"http_{legacy_http_status}", legacy_http_status
    if text:
        return "source_error", None
    return None, None


def _public_copy(
    status: str,
    *,
    source_failed: bool,
    has_baseline: bool,
    failure_kind: str | None,
) -> tuple[str, str, str]:
    if status == "healthy":
        return (
            "재고 데이터 정상",
            "Tesla 재고 소스를 정상적으로 확인했습니다.",
            "SOURCE HEALTHY",
        )
    if source_failed and has_baseline:
        if failure_kind in {"access_denied", "http_403"}:
            message = (
                "Tesla 재고 소스가 자동 요청을 거부해 최신 가격과 판매 여부를 확인하지 "
                "못했습니다. 마지막으로 확인된 스냅샷을 보존해 표시합니다."
            )
        elif failure_kind in {"rate_limited", "http_429"}:
            message = (
                "Tesla 재고 소스의 요청 제한으로 최신 가격과 판매 여부를 확인하지 못했습니다. "
                "마지막으로 확인된 스냅샷을 보존해 표시합니다."
            )
        else:
            message = (
                "Tesla 재고 소스를 갱신하지 못했습니다. 마지막으로 확인된 스냅샷을 보존해 "
                "표시합니다."
            )
        return "재고 갱신 지연", message, "SOURCE DEGRADED"
    if has_baseline:
        return (
            "마지막 확인 데이터",
            "마지막으로 확인된 재고 스냅샷이 갱신 주기를 지났습니다. 최신 가격과 판매 여부는 "
            "Tesla에서 다시 확인하세요.",
            "SOURCE DEGRADED",
        )
    return (
        "재고를 불러오지 못했습니다",
        "Tesla 재고 소스를 확인하지 못했고 표시할 마지막 스냅샷도 없습니다.",
        "SOURCE FAILED",
    )


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
    failure_kind, failure_http_status = _failure_metadata(
        failure_reason,
        error_code=internal.get("last_error_code"),
        http_status=internal.get("last_http_status"),
    )
    if not source_failed and public_status != "healthy":
        failure_kind = "stale" if has_baseline else "no_baseline"
        failure_http_status = None
    headline, message, health_label = _public_copy(
        public_status,
        source_failed=source_failed,
        has_baseline=has_baseline,
        failure_kind=failure_kind,
    )
    if public_status == "healthy":
        data_mode = "live"
    elif has_baseline:
        data_mode = "last_known"
    else:
        data_mode = "unavailable"
    inventory_source = inventory.get("source") if isinstance(inventory, dict) else None
    source_document = inventory_source if isinstance(inventory_source, dict) else {}
    is_seed_snapshot = bool(source_document.get("seed_snapshot"))
    baseline_kind = "seed_snapshot" if is_seed_snapshot else "live_crawl" if has_baseline else "none"
    last_verified = _inventory_timestamp(inventory, last_successful)
    return {
        "schema_version": 1,
        "status": public_status,
        "headline": headline,
        "message": message,
        "health_label": health_label,
        "data_mode": data_mode,
        "baseline_kind": baseline_kind,
        "last_verified_snapshot": last_verified,
        "failure_reason": failure_reason,
        "failure_kind": failure_kind,
        "failure_http_status": failure_http_status,
        "last_successful_crawl": last_successful,
        "last_attempted_crawl": internal.get("last_attempt_at"),
        "stale": stale,
        "current_candidates": candidate_count,
        "last_known_candidates": candidate_count if has_baseline else 0,
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
