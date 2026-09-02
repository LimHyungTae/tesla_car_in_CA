"""One safe monitor cycle: cadence, fetch, normalize, diff, persist."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Protocol

from .cadence import is_due, is_stale, next_due_at, parse_instant, utc_iso
from .changes import TIER_RANK, detect_changes
from .config import configured_paths, load_configs
from .evaluation import evaluate_vehicle, neutral_color_status, normalize_vehicle
from .source import FetchResult, ParserError, SourceError, TeslaInventoryClient
from .storage import atomic_write_json, read_json, sync_dashboard


class InventoryClient(Protocol):
    def fetch(self) -> FetchResult: ...


@dataclass(frozen=True)
class RunResult:
    status: str
    attempted: bool
    success: bool
    observed_at: str
    inventory_count: int
    event_count: int
    alert_count: int
    stale: bool
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "last_run_at": None,
        "last_attempt_at": None,
        "last_successful_at": None,
        "last_status": "never_run",
        "last_error": None,
        "consecutive_failures": 0,
        "stale": True,
        "known_vins": [],
        "inactive_vins": [],
        "catalog": {},
    }


def _default_history() -> dict[str, Any]:
    return {"schema_version": 1, "updated_at": None, "runs": [], "events": []}


def _inventory_vehicles(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return [item for item in document if isinstance(item, dict)]
    if isinstance(document, dict) and isinstance(document.get("vehicles"), list):
        return [item for item in document["vehicles"] if isinstance(item, dict)]
    return []


def _append_run(history: dict[str, Any], run: Mapping[str, Any], monitor: Mapping[str, Any]) -> None:
    history.setdefault("runs", []).append(dict(run))
    limit = max(1, int(monitor.get("history", {}).get("maximum_runs", 500)))
    history["runs"] = history["runs"][-limit:]


def _append_events(history: dict[str, Any], events: list[dict[str, Any]], monitor: Mapping[str, Any]) -> None:
    history.setdefault("events", []).extend(events)
    limit = max(1, int(monitor.get("history", {}).get("maximum_events", 5000)))
    history["events"] = history["events"][-limit:]


def _decorate(record: dict[str, Any], buy_box: Mapping[str, Any], observed_at: str) -> dict[str, Any]:
    evaluation = evaluate_vehicle(record, buy_box)
    result = dict(record)
    result.update(
        {
            "observed_at": observed_at,
            "tier": evaluation["tier"],
            "strength": evaluation["strength"],
            "opportunity_tier": evaluation["opportunity_tier"],
            "monitor_tier": evaluation["monitor_tier"],
            "verification": evaluation["verification"],
            "evaluation": evaluation,
        }
    )
    return result


def _preserve_observation_history(
    vehicle: dict[str, Any],
    previous: Mapping[str, Any] | None,
    observed_at: str,
) -> dict[str, Any]:
    """Attach stable first/last-seen and one-cycle price movement fields."""

    result = dict(vehicle)
    prior = previous or {}
    first_seen = prior.get("first_seen_at") or observed_at
    prior_price = prior.get("price_usd")
    current_price = result.get("price_usd")
    price_change = None
    if current_price is not None and prior_price is not None:
        price_change = int(current_price) - int(prior_price)
    result.update(
        {
            "first_seen_at": first_seen,
            "last_seen_at": observed_at,
            "previous_price_usd": int(prior_price) if prior_price is not None else None,
            "price_change_usd": price_change,
        }
    )
    return result


def _preserve_verified_metadata(
    vehicle: dict[str, Any], previous: Mapping[str, Any] | None, observed_at: str
) -> dict[str, Any]:
    """Carry forward evidence the sparse live feed omitted, never inventing it."""

    result = dict(vehicle)
    prior = previous or {}
    history_fields = ("title_status", "accident_or_damage", "prior_use", "autocheck_score")
    current_history_fields = [field for field in history_fields if result.get(field) is not None]
    previous_history_fields = [field for field in history_fields if prior.get(field) is not None]
    carried_history_fields: list[str] = []
    for field in history_fields:
        if result.get(field) is None and prior.get(field) is not None:
            result[field] = prior[field]
            carried_history_fields.append(field)

    if current_history_fields:
        current_source = result.get("history_source") or "Tesla official inventory v4"
        result["history_source"] = current_source
        result["history_verified_at"] = result.get("history_verified_at") or observed_at
        if carried_history_fields:
            result["history_evidence_status"] = "mixed_current_and_last_known"
            result["history_last_known_fields"] = carried_history_fields
            result["history_last_known_source"] = prior.get("history_source")
            result["history_last_known_verified_at"] = prior.get("history_verified_at")
        else:
            result["history_evidence_status"] = "current_source"
    elif previous_history_fields:
        result["history_source"] = prior.get("history_source")
        result["history_verified_at"] = prior.get("history_verified_at")
        result["history_evidence_status"] = "last_known"
        result["history_last_known_fields"] = previous_history_fields
    else:
        result["history_evidence_status"] = "unverified"

    current_battery = str(result.get("battery_health") or "unknown").casefold() != "unknown"
    previous_battery = (
        str(prior.get("battery_health") or "unknown").casefold() != "unknown"
    )
    if current_battery:
        result["battery_health_source"] = (
            result.get("battery_health_source") or "Tesla official inventory v4"
        )
        result["battery_health_checked_at"] = result.get("battery_health_checked_at") or observed_at
        result["battery_evidence_status"] = "current_source"
    elif previous_battery:
        result["battery_health"] = prior["battery_health"]
        result["battery_health_source"] = prior.get("battery_health_source")
        result["battery_health_checked_at"] = prior.get("battery_health_checked_at")
        result["battery_evidence_status"] = "last_known"
    else:
        result["battery_evidence_status"] = "unverified"

    nullable_fields = (
        "hardware",
        "wheel_inches",
        "seat_count",
        "location",
        "exterior",
        "interior",
        "vehicle_history_label",
        "cached_transfer_fee_usd",
        "has_fsd",
        "source_first_seen_at",
        "source_last_seen_at",
        "source_previous_price_usd",
    )
    for field in nullable_fields:
        if result.get(field) is None and prior.get(field) is not None:
            result[field] = prior[field]
    if not result.get("data_conflicts") and prior.get("data_conflicts"):
        result["data_conflicts"] = prior["data_conflicts"]
    return result


def _in_candidate_scope(
    vehicle: Mapping[str, Any], monitor: Mapping[str, Any], buy_box: Mapping[str, Any]
) -> bool:
    """Keep the configured search pool while retaining gate failures like 20-inch wheels."""

    gates = buy_box["vehicle_gates"]
    known_checks = (
        (vehicle.get("model"), gates["model"]),
        (vehicle.get("hardware"), gates["required_hardware"]),
    )
    if any(value is not None and value != expected for value, expected in known_checks):
        return False
    trim = vehicle.get("trim")
    if trim is not None and trim not in gates["accepted_trims"]:
        return False
    year = vehicle.get("year")
    if year is not None and int(year) < int(gates["minimum_year"]):
        return False
    mileage = vehicle.get("mileage")
    if mileage is not None and int(mileage) >= int(gates["maximum_mileage_exclusive"]):
        return False
    return neutral_color_status(vehicle, monitor) is not False


def _sort_key(vehicle: Mapping[str, Any]) -> tuple[Any, ...]:
    rank = TIER_RANK.get(str(vehicle.get("monitor_tier") or "WAIT"), 1)
    return (-rank, vehicle.get("price_usd") is None, vehicle.get("price_usd") or 10**9, vehicle.get("mileage") or 10**9)


def _write_status_and_history(
    paths: dict[str, Path], state: dict[str, Any], history: dict[str, Any], observed_at: str
) -> None:
    history["updated_at"] = observed_at
    atomic_write_json(paths["history"], history)
    atomic_write_json(paths["state"], state)
    sync_dashboard(paths)


def run_monitor(
    root: Path | str = ".",
    *,
    force: bool = False,
    now: datetime | str | None = None,
    client: InventoryClient | None = None,
) -> RunResult:
    root_path = Path(root).resolve()
    monitor, buy_box = load_configs(root_path)
    paths = configured_paths(root_path, monitor)
    current_time = parse_instant(now, str(monitor.get("timezone", "America/Los_Angeles")))
    observed_at = utc_iso(current_time)
    state = read_json(paths["state"], _default_state(), strict=True)
    if not isinstance(state, dict):
        state = _default_state()
    state = {**_default_state(), **state}
    history = read_json(paths["history"], _default_history(), strict=True)
    if not isinstance(history, dict):
        history = _default_history()
    history = {**_default_history(), **history}
    previous_document = read_json(paths["inventory"], {}, strict=True)
    previous_vehicles = _inventory_vehicles(previous_document)
    previous_by_vin = {
        str(item["vin"]): item for item in previous_vehicles if item.get("vin")
    }
    catalog = state.get("catalog", {})
    if not isinstance(catalog, Mapping):
        catalog = {}

    if not is_due(current_time, state.get("last_successful_at"), monitor, force=force):
        stale = is_stale(current_time, state.get("last_successful_at"), monitor)
        # A scheduler wake-up is not a source attempt. Leave persisted state
        # byte-for-byte unchanged so cadence guards do not create noisy bot
        # commits or redundant Pages deployments.
        return RunResult("skipped", False, True, observed_at, len(previous_vehicles), 0, 0, stale)

    state["last_attempt_at"] = observed_at
    source_client = client or TeslaInventoryClient(monitor["source"])
    try:
        fetched = source_client.fetch()
        if not isinstance(fetched, FetchResult):
            raise ParserError("Inventory client returned an invalid result")
        raw_vehicles = fetched.vehicles
        if not raw_vehicles and not bool(monitor["source"].get("allow_empty_inventory", False)):
            raise ParserError("Empty source result rejected to protect the last active inventory")
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in raw_vehicles:
            vehicle = normalize_vehicle(raw, monitor["source"])
            vin = vehicle.get("vin")
            if not vin:
                raise ParserError("Inventory record is missing VIN")
            if vehicle.get("price_usd") is None or vehicle.get("mileage") is None:
                raise ParserError(f"Inventory record {vin} is missing price or mileage")
            vehicle["neutral_color"] = neutral_color_status(vehicle, monitor)
            if not _in_candidate_scope(vehicle, monitor, buy_box):
                continue
            if vin in seen:
                continue
            seen.add(vin)
            prior = previous_by_vin.get(str(vin)) or catalog.get(str(vin))
            vehicle = _preserve_verified_metadata(vehicle, prior, observed_at)
            normalized.append(
                _decorate(
                    _preserve_observation_history(vehicle, prior, observed_at),
                    buy_box,
                    observed_at,
                )
            )
        if previous_vehicles and not normalized and not bool(
            monitor["source"].get("allow_empty_inventory", False)
        ):
            raise ParserError("Empty normalized result rejected to protect the last active inventory")
        normalized.sort(key=_sort_key)
        events, known, inactive, catalog = detect_changes(
            previous_vehicles,
            normalized,
            observed_at=observed_at,
            known_vins=state.get("known_vins", []),
            inactive_vins=state.get("inactive_vins", []),
            catalog=catalog,
            price_drop_alert_usd=int(monitor.get("changes", {}).get("price_drop_alert_usd", 300)),
        )
        alert_count = sum(1 for event in events if event.get("alert"))
        inventory = {
            "schema_version": 1,
            "generated_at": observed_at,
            "source_successful_at": observed_at,
            "source": {
                "name": monitor["source"].get("name", "Tesla official inventory v4"),
                "base_url": monitor["source"].get("base_url"),
                "zip": str(monitor["source"].get("zip", "94404")),
                "radius_miles": int(
                    monitor["source"].get("radius_miles", monitor["source"].get("radius", 200))
                ),
                "page_count": fetched.page_count,
                "reported_total": fetched.reported_total,
                "no_price_floor": True,
            },
            "count": len(normalized),
            "vehicles": normalized,
        }
        run = {
            "observed_at": observed_at,
            "status": "success",
            "inventory_count": len(normalized),
            "event_count": len(events),
            "alert_count": alert_count,
        }
        _append_events(history, events, monitor)
        _append_run(history, run, monitor)
        state.update(
            {
                "last_run_at": observed_at,
                "last_attempt_at": observed_at,
                "last_successful_at": observed_at,
                "last_status": "success",
                "last_error": None,
                "consecutive_failures": 0,
                "stale": False,
                "inventory_count": len(normalized),
                "last_event_count": len(events),
                "last_alert_count": alert_count,
                "known_vins": sorted(known),
                "inactive_vins": sorted(inactive),
                "catalog": catalog,
                "next_due_at": next_due_at(current_time, observed_at, monitor),
            }
        )
        # Inventory is written only after a complete, parsed source response.
        atomic_write_json(paths["inventory"], inventory)
        _write_status_and_history(paths, state, history, observed_at)
        return RunResult("success", True, True, observed_at, len(normalized), len(events), alert_count, False)
    except SourceError as exc:
        state.update(
            {
                "last_run_at": observed_at,
                "last_attempt_at": observed_at,
                "last_status": "source_error",
                "last_error": str(exc),
                "consecutive_failures": int(state.get("consecutive_failures", 0)) + 1,
                "stale": True,
                "inventory_count": len(previous_vehicles),
                "next_due_at": observed_at,
            }
        )
        run = {
            "observed_at": observed_at,
            "status": "source_error",
            "error": str(exc),
            "inventory_count_preserved": len(previous_vehicles),
        }
        _append_run(history, run, monitor)
        # Crucially, data/inventory.json is not written in this branch.
        _write_status_and_history(paths, state, history, observed_at)
        return RunResult(
            "source_error",
            True,
            False,
            observed_at,
            len(previous_vehicles),
            0,
            0,
            True,
            str(exc),
        )
