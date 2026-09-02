"""Inventory diffing and alert-worthy event detection."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping


TIER_RANK = {
    "EXCLUDE": 0,
    "NONE": 1,
    "WAIT": 1,
    "FAIR": 2,
    "BUY": 3,
    "HIGH PRIORITY": 4,
    "ULTRA VALUE": 5,
}
ALERT_TIERS = {"BUY", "HIGH PRIORITY", "ULTRA VALUE"}


def _tier(vehicle: Mapping[str, Any]) -> str:
    direct = vehicle.get("monitor_tier")
    if direct:
        return str(direct)
    evaluation = vehicle.get("evaluation")
    if isinstance(evaluation, Mapping):
        return str(evaluation.get("monitor_tier") or evaluation.get("tier") or "WAIT")
    return str(vehicle.get("tier") or "WAIT")


def _event(
    observed_at: str,
    event_type: str,
    vin: str,
    *,
    before: Any = None,
    after: Any = None,
    alert: bool = False,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "observed_at": observed_at,
        "type": event_type,
        "vin": vin,
        "alert": alert,
    }
    if before is not None:
        result["before"] = before
    if after is not None:
        result["after"] = after
    if details:
        result["details"] = dict(details)
    return result


def _catalog_record(vehicle: Mapping[str, Any]) -> dict[str, Any]:
    # Normalized source records are already JSON-safe. Keeping the complete
    # snapshot lets a later disappearance render a useful card without having
    # to query a VIN that Tesla has removed from the active feed.
    return deepcopy(dict(vehicle))


def detect_changes(
    previous_vehicles: Iterable[Mapping[str, Any]],
    current_vehicles: Iterable[Mapping[str, Any]],
    *,
    observed_at: str,
    known_vins: Iterable[str] = (),
    inactive_vins: Iterable[str] = (),
    catalog: Mapping[str, Mapping[str, Any]] | None = None,
    price_drop_alert_usd: int = 300,
) -> tuple[list[dict[str, Any]], set[str], set[str], dict[str, dict[str, Any]]]:
    previous = {str(item["vin"]): item for item in previous_vehicles if item.get("vin")}
    current = {str(item["vin"]): item for item in current_vehicles if item.get("vin")}
    known = set(known_vins) | set(previous)
    inactive = set(inactive_vins)
    stored = {str(key): deepcopy(dict(value)) for key, value in (catalog or {}).items()}
    events: list[dict[str, Any]] = []

    for vin in sorted(current):
        now = current[vin]
        old = previous.get(vin) or stored.get(vin)
        if vin in inactive:
            events.append(
                _event(
                    observed_at,
                    "reappeared",
                    vin,
                    after={"price_usd": now.get("price_usd"), "monitor_tier": _tier(now)},
                    alert=_tier(now) in ALERT_TIERS,
                )
            )
        elif vin not in known:
            events.append(
                _event(
                    observed_at,
                    "new",
                    vin,
                    after={"price_usd": now.get("price_usd"), "monitor_tier": _tier(now)},
                    alert=_tier(now) in ALERT_TIERS,
                )
            )

        if old is not None:
            old_price, new_price = old.get("price_usd"), now.get("price_usd")
            if old_price is not None and new_price is not None and old_price != new_price:
                delta = int(new_price) - int(old_price)
                event_type = "price_decrease" if delta < 0 else "price_increase"
                events.append(
                    _event(
                        observed_at,
                        event_type,
                        vin,
                        before=int(old_price),
                        after=int(new_price),
                        alert=delta <= -abs(int(price_drop_alert_usd)),
                        details={"delta_usd": delta},
                    )
                )
            for field, event_type in (("mileage", "mileage_change"), ("location", "location_change")):
                before, after = old.get(field), now.get(field)
                if before is not None and after is not None and before != after:
                    details = None
                    if field == "mileage":
                        details = {"delta_miles": int(after) - int(before)}
                    events.append(
                        _event(
                            observed_at,
                            event_type,
                            vin,
                            before=before,
                            after=after,
                            details=details,
                        )
                    )
            old_tier, new_tier = _tier(old), _tier(now)
            old_rank, new_rank = TIER_RANK.get(old_tier, 1), TIER_RANK.get(new_tier, 1)
            if new_rank > old_rank:
                events.append(
                    _event(
                        observed_at,
                        "tier_upgrade",
                        vin,
                        before=old_tier,
                        after=new_tier,
                        alert=True,
                    )
                )
            elif new_rank < old_rank:
                events.append(
                    _event(
                        observed_at,
                        "tier_downgrade",
                        vin,
                        before=old_tier,
                        after=new_tier,
                    )
                )

    for vin in sorted(set(previous) - set(current)):
        old = previous[vin]
        events.append(
            _event(
                observed_at,
                "disappeared",
                vin,
                before=_catalog_record(old),
            )
        )
        inactive.add(vin)

    inactive.difference_update(current)
    known.update(current)
    for vin, vehicle in current.items():
        stored[vin] = _catalog_record(vehicle)
    for vin, vehicle in previous.items():
        stored.setdefault(vin, _catalog_record(vehicle))
    return events, known, inactive, stored
