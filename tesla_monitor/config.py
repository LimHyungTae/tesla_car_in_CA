"""Configuration loading with conservative, repository-local defaults."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping


DEFAULT_MONITOR_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "timezone": "America/Los_Angeles",
    "cadence": {
        "night_start_hour": 0,
        "night_end_hour_exclusive": 5,
        "night_minutes": 15,
        "day_minutes": 30,
        "stale_multiplier": 2,
    },
    "source": {
        "base_url": "https://www.tesla.com/inventory/api/v4/inventory-results",
        "market": "US",
        "language": "en",
        "model": "my",
        "condition": "used",
        "zip": "94404",
        "radius": 200,
        "lat": 37.5538,
        "lng": -122.2711,
        "page_size": 50,
        "max_pages": 10,
        "timeout_seconds": 20,
        "max_attempts": 3,
        "backoff_seconds": 2,
        "allow_empty_inventory": False,
    },
    "changes": {"price_drop_alert_usd": 300},
    "history": {"maximum_runs": 500, "maximum_events": 5000},
    "paths": {
        "state": "data/state.json",
        "history": "data/history.json",
        "inventory": "data/inventory.json",
        "dashboard_status": "dashboard/data/status.json",
        "dashboard_history": "dashboard/data/history.json",
        "dashboard_inventory": "dashboard/data/inventory.json",
        "buy_box_config": "config/buy-box.json",
        "monitor_config": "config/monitor.json",
        "dashboard_buy_box_config": "dashboard/data/buy-box.json",
        "dashboard_monitor_config": "dashboard/data/monitor.json",
    },
}


class ConfigError(ValueError):
    """Raised when a required configuration file is invalid."""


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_json(path: Path, *, required: bool = True) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise ConfigError(f"Required configuration does not exist: {path}")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Could not read JSON configuration {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigError(f"Configuration must be a JSON object: {path}")
    return value


def load_configs(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load monitor and Buy Box configs.

    ``monitor.json`` is merged over safe defaults so newer optional keys do not
    break older checkouts. ``buy-box.json`` is required because its gates are
    the decision contract.
    """

    monitor_file = root / "config" / "monitor.json"
    buy_box_file = root / "config" / "buy-box.json"
    monitor = _deep_merge(
        DEFAULT_MONITOR_CONFIG,
        load_json(monitor_file, required=False),
    )
    buy_box = load_json(buy_box_file, required=True)
    return monitor, buy_box


def configured_paths(root: Path, monitor: Mapping[str, Any]) -> dict[str, Path]:
    raw = _deep_merge(DEFAULT_MONITOR_CONFIG["paths"], monitor.get("paths", {}))
    return {key: (root / str(value)).resolve() for key, value in raw.items()}
