"""Normalize Tesla records and apply Buy Box v2 deterministically."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


def _key_map(record: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key).casefold(): value for key, value in record.items()}


def pick(record: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    mapped = _key_map(record)
    for name in names:
        if name in record and record[name] is not None:
            return record[name]
        value = mapped.get(name.casefold())
        if value is not None:
            return value
    return default


def _number(value: Any, *, integer: bool = False) -> float | int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None
    return int(round(number)) if integer else number


def _money(value: Any) -> int | None:
    number = _number(value)
    if number is None:
        return None
    # Tesla uses dollars for Price but cents for fields such as TransportFee.
    if number >= 1_000_000:
        number /= 100
    return int(round(number))


def _transport_money(value: Any) -> int | None:
    number = _number(value)
    if number is None:
        return None
    # Transport is normally $0–$2,500; Tesla's feed commonly serializes it in cents.
    if number > 10_000:
        number /= 100
    return int(round(number))


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, Mapping):
        for key in ("name", "label", "title", "value", "description", "code"):
            if value.get(key):
                return str(value[key]).strip()
    if isinstance(value, list):
        for item in value:
            text = _text(item)
            if text:
                return text
    return str(value).strip() or None


def _option_codes(record: Mapping[str, Any]) -> set[str]:
    raw = pick(record, "OptionCodeList", "optionCodeList", "option_codes", default="")
    if isinstance(raw, list):
        values: Iterable[Any] = raw
    else:
        values = str(raw or "").split(",")
    return {str(code).strip().upper().lstrip("$") for code in values if str(code).strip()}


def _wheel_inches(record: Mapping[str, Any], codes: set[str]) -> int | None:
    raw = pick(record, "WheelSize", "wheel_inches", "Wheels", "wheels")
    if isinstance(raw, (int, float)):
        return int(raw)
    text = (_text(raw) or "").lower()
    if "19" in text or "nineteen" in text:
        return 19
    if "20" in text or "twenty" in text:
        return 20
    if "21" in text or "twenty-one" in text:
        return 21
    for size in (19, 20, 21):
        if any(code.startswith(f"WY{size}") for code in codes):
            return size
    return None


def _seat_count(record: Mapping[str, Any], codes: set[str]) -> int | None:
    raw = pick(record, "SeatCount", "seats", "CabinConfig", "cabinConfig")
    number = _number(raw, integer=True)
    if number is not None:
        return int(number)
    text = (_text(raw) or "").lower()
    if "five" in text:
        return 5
    if "seven" in text:
        return 7
    if "STY7S" in codes:
        return 7
    if "STY5S" in codes:
        return 5
    return None


def _location(record: Mapping[str, Any]) -> str | None:
    direct = _text(pick(record, "Location", "location", "MetroName", "metroName"))
    city = _text(pick(record, "City", "locationCity", "city"))
    state = _text(pick(record, "StateProvince", "locationState", "state"))
    if city and state:
        return f"{city}, {state}"
    return city or direct or state


def _paint(record: Mapping[str, Any], codes: set[str]) -> str | None:
    raw = _text(pick(record, "PAINT", "Paint", "ExteriorColor", "exteriorColor"))
    known = {
        "PBSB": "Solid Black",
        "PPSW": "Pearl White Multi-Coat",
        "PMNG": "Midnight Silver Metallic",
        "PMSG": "Midnight Silver Metallic",
        "PN01": "Quicksilver",
        "PPMR": "Red Multi-Coat",
        "PPSB": "Deep Blue Metallic",
        "PR00": "Ultra Red",
    }
    if raw:
        code = raw.upper().lstrip("$")
        return known.get(code, raw)
    for code, label in known.items():
        if code in codes:
            return label
    return None


def _history(record: Mapping[str, Any]) -> tuple[bool | None, str | None]:
    raw_history = _text(pick(record, "VehicleHistory", "vehicleHistory"))
    disclosure = pick(record, "DamageDisclosure", "damageDisclosure")
    accident: bool | None = None
    if raw_history:
        lowered = raw_history.casefold()
        negative_phrases = (
            "no accident",
            "no reported accident",
            "without accident",
            "accident free",
            "accident-free",
            "no damage",
            "no reported damage",
            "without damage",
            "damage free",
            "damage-free",
            "clean",
        )
        if any(phrase in lowered for phrase in negative_phrases):
            accident = False
        elif "accident" in lowered or "damage" in lowered:
            accident = True

    disclosure_damage: bool | None = None
    if isinstance(disclosure, bool):
        disclosure_damage = disclosure
    elif isinstance(disclosure, (int, float)) and not isinstance(disclosure, bool):
        disclosure_damage = disclosure != 0
    elif disclosure not in (None, "", [], {}):
        disclosure_text = (_text(disclosure) or "").strip().casefold()
        false_values = {
            "0",
            "false",
            "n",
            "no",
            "none",
            "null",
            "clean",
            "not reported",
            "no damage",
            "no damage reported",
        }
        true_values = {"1", "true", "y", "yes", "reported", "damage reported"}
        if disclosure_text in false_values or disclosure_text.startswith("no "):
            disclosure_damage = False
        elif disclosure_text in true_values or "damage" in disclosure_text:
            disclosure_damage = True
    if disclosure_damage is True:
        accident = True
    elif disclosure_damage is False and accident is None:
        accident = False
    clean_title = pick(record, "CleanTitle", "cleanTitle")
    title_status: str | None = None
    if clean_title is True:
        title_status = "clean"
    elif clean_title is False:
        title_status = "not clean"
    else:
        title_brand = _text(pick(record, "TitleBrand", "titleBrand"))
        if title_brand:
            title_status = "clean" if title_brand.casefold() == "clean" else title_brand
    return accident, title_status


def normalize_vehicle(record: Mapping[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    codes = _option_codes(record)
    accident, title_status = _history(record)
    vin = _text(pick(record, "VIN", "vin"))
    price = _money(pick(record, "Price", "purchasePrice", "currentPrice", "price_usd"))
    mileage = _number(pick(record, "Odometer", "Mileage", "mileage"), integer=True)
    year = _number(pick(record, "Year", "year"), integer=True)
    model_raw = _text(pick(record, "ModelName", "modelName", "Model", "model")) or "Model Y"
    model = "Model Y" if model_raw.casefold() in {"my", "model y", "y"} else model_raw
    trim = _text(pick(record, "TrimName", "trimName", "Trim", "trim"))
    hardware = _text(
        pick(
            record,
            "HardwareVersion",
            "hardwareVersion",
            "AutopilotHardwareVersion",
            "AutopilotHardware",
            "APHardware",
            "hardware",
        )
    )
    if hardware:
        compact = hardware.upper().replace(" ", "")
        if compact in {"4", "HW4", "AP4", "AI4"}:
            hardware = "HW4"
    if hardware is None and any(code in {"HW4", "AP4", "AI4"} for code in codes):
        hardware = "HW4"
    accident_history = _text(pick(record, "VehicleHistory", "vehicleHistory"))
    prior_use = _text(pick(record, "PriorUse", "priorUse", "VehicleUsage", "vehicleUsage"))
    battery_health = _text(pick(record, "BatteryHealth", "batteryHealth")) or "unknown"
    transport = _transport_money(pick(record, "TransportFee", "transportFee", "transport_fee_usd"))
    exterior = _paint(record, codes)
    interior = _text(pick(record, "INTERIOR", "Interior", "InteriorColor", "interiorColor"))
    fsd_raw = pick(record, "HasFsd", "hasFsd", "FullSelfDriving", "fullSelfDriving")
    has_fsd = fsd_raw if isinstance(fsd_raw, bool) else None
    condition = (_text(pick(record, "InventoryType", "Condition", "condition")) or source.get("condition", "used"))
    tesla_cpo = str(condition).casefold() in {"used", "pre-owned", "preowned", "cpo"}
    return {
        "vin": vin,
        "available": True,
        "model": model,
        "trim": trim,
        "year": year,
        "hardware": hardware,
        "wheel_inches": _wheel_inches(record, codes),
        "seat_count": _seat_count(record, codes),
        "mileage": mileage,
        "price_usd": price,
        "location": _location(record),
        "exterior": exterior,
        "interior": interior,
        "tesla_cpo": tesla_cpo,
        "title_status": title_status,
        "accident_or_damage": accident,
        "vehicle_history_label": accident_history,
        "autocheck_score": _number(
            pick(record, "AutoCheckScore", "autocheckScore", "autocheck_score"),
            integer=True,
        ),
        "prior_use": prior_use,
        "battery_health": battery_health.casefold(),
        "battery_health_checked_at": _text(
            pick(record, "BatteryHealthCheckedAt", "batteryHealthCheckedAt")
        ),
        "battery_health_source": _text(
            pick(record, "BatteryHealthSource", "batteryHealthSource", "battery_health_source")
        ),
        "battery_evidence_status": _text(
            pick(record, "BatteryEvidenceStatus", "batteryEvidenceStatus")
        ),
        "history_verified_at": _text(
            pick(record, "HistoryVerifiedAt", "historyVerifiedAt")
        ),
        "history_source": _text(
            pick(record, "HistorySource", "historySource", "history_source")
        ),
        "history_evidence_status": _text(
            pick(record, "HistoryEvidenceStatus", "historyEvidenceStatus")
        ),
        "transport_fee_usd": transport,
        "cached_transfer_fee_usd": _transport_money(
            pick(record, "CachedTransferFee", "cachedTransferFee", "cached_transfer_fee_usd")
        ),
        "has_fsd": has_fsd,
        "option_codes": sorted(codes),
        "tesla_url": _text(pick(record, "TeslaUrl", "teslaUrl"))
        or (f"https://www.tesla.com/my/order/{vin}?titleStatus=used&redirect=no#overview" if vin else None),
        "source_first_seen_at": _text(
            pick(record, "FirstSeenAt", "firstSeenAt", "first_seen_at")
        ),
        "source_last_seen_at": _text(pick(record, "LastSeenAt", "lastSeenAt")),
        "source_previous_price_usd": _money(
            pick(
                record,
                "PreviousPrice",
                "previousPrice",
                "PreviousPriceUsd",
                "previous_price_usd",
            )
        ),
        "raw_rewards": pick(record, "Rewards", "rewards", default=[]),
        "data_conflicts": pick(record, "DataConflicts", "dataConflicts", "data_conflicts", default=[]),
    }


def neutral_color_status(vehicle: Mapping[str, Any], monitor: Mapping[str, Any]) -> bool | None:
    """Return True/False for a known paint, or None when the source omitted paint."""

    allowed = monitor.get("filters", {}).get("neutral_colors")
    if not isinstance(allowed, list) or not allowed:
        return True
    exterior = vehicle.get("exterior")
    if not exterior:
        return None

    def normalized(value: Any) -> str:
        return " ".join(str(value).casefold().replace("gray", "grey").replace("-", " ").split())

    paint = normalized(exterior)
    return any(
        (candidate := normalized(item)) == paint
        or candidate in paint
        or paint in candidate
        for item in allowed
    )


def estimate_otd(price_usd: int, transport_usd: int, buy_box: Mapping[str, Any]) -> dict[str, float]:
    market = buy_box["market"]
    tax = float(market["sales_tax_rate"])
    fees = market["estimated_fixed_fees_usd"]
    taxable = price_usd + transport_usd
    return {
        "low": round(taxable * (1 + tax) + float(fees["low"]), 2),
        "high": round(taxable * (1 + tax) + float(fees["high"]), 2),
    }


def maximum_listing_price(transport_usd: int, buy_box: Mapping[str, Any]) -> float:
    market = buy_box["market"]
    return (
        (float(market["max_otd_usd"]) - float(market["estimated_fixed_fees_usd"]["high"]))
        / (1 + float(market["sales_tax_rate"]))
        - transport_usd
    )


def _matches_price_mileage_band(
    price: int, mileage: int, band: Mapping[str, Any] | None
) -> bool:
    """Match either one price/mileage ceiling or an ``any_of`` list of ceilings."""

    if not isinstance(band, Mapping):
        return False
    choices = band.get("any_of")
    if not isinstance(choices, list):
        choices = [band]
    for choice in choices:
        if not isinstance(choice, Mapping):
            continue
        maximum_price = choice.get("maximum_listing_price_usd")
        maximum_mileage = choice.get("maximum_mileage")
        if maximum_price is None or maximum_mileage is None:
            continue
        if price <= int(maximum_price) and mileage <= int(maximum_mileage):
            return True
    return False


def _maximum_band_price(band: Mapping[str, Any] | None, default: int) -> int:
    if not isinstance(band, Mapping):
        return default
    choices = band.get("any_of")
    if not isinstance(choices, list):
        choices = [band]
    prices = [
        int(item["maximum_listing_price_usd"])
        for item in choices
        if isinstance(item, Mapping) and item.get("maximum_listing_price_usd") is not None
    ]
    return max(prices, default=default)


def evaluate_vehicle(vehicle: Mapping[str, Any], buy_box: Mapping[str, Any]) -> dict[str, Any]:
    gates = buy_box["vehicle_gates"]
    bands = buy_box["price_mileage_bands"]
    failures: list[str] = []
    pending: list[str] = []

    def required_equal(value: Any, expected: Any, missing: str, failure: str) -> None:
        if value is None:
            pending.append(missing)
        elif value != expected:
            failures.append(failure)

    if vehicle.get("available") is False:
        failures.append("not currently available")
    required_equal(vehicle.get("model"), gates["model"], "model", "wrong model")
    trim = vehicle.get("trim")
    if trim is None:
        pending.append("exact trim")
    elif trim not in gates["accepted_trims"]:
        failures.append("wrong trim")
    year = vehicle.get("year")
    if year is None:
        pending.append("model year")
    elif int(year) < int(gates["minimum_year"]):
        failures.append("model year below minimum")
    required_equal(vehicle.get("hardware"), gates["required_hardware"], "HW4", "not HW4")
    required_equal(
        vehicle.get("wheel_inches"),
        int(gates["required_wheel_inches"]),
        "wheel size",
        "not 19-inch wheels",
    )
    if "neutral_color" in vehicle:
        if vehicle.get("neutral_color") is None:
            pending.append("exterior color")
        elif vehicle.get("neutral_color") is False:
            failures.append("excluded exterior color")
    mileage = vehicle.get("mileage")
    if mileage is None:
        pending.append("mileage")
    elif int(mileage) >= int(gates["maximum_mileage_exclusive"]):
        failures.append("50,000mi or more")
    required_equal(vehicle.get("tesla_cpo"), True, "Tesla CPO status", "not Tesla CPO")

    title = vehicle.get("title_status")
    if title is None:
        pending.append("title status")
    elif str(title).strip().casefold() != "clean":
        failures.append("title is not clean")
    accident = vehicle.get("accident_or_damage")
    if accident is None:
        pending.append("accident/damage history")
    elif accident is True:
        failures.append("reported accident/damage")
    prior_use = vehicle.get("prior_use")
    if prior_use is None:
        pending.append("prior use")
    else:
        normalized_prior_use = " ".join(str(prior_use).strip().casefold().replace("-", " ").split())
        excluded_uses = {
            " ".join(str(value).strip().casefold().replace("-", " ").split())
            for value in gates["excluded_prior_use"]
        }
        if any(excluded in normalized_prior_use for excluded in excluded_uses):
            failures.append(f"excluded prior use: {prior_use}")
    health = str(vehicle.get("battery_health") or "unknown").strip().casefold()
    if health == "issue":
        failures.append("Battery Health issue")
    elif health not in {"clear", "pass", "healthy"}:
        pending.append("Battery Health/SOH")

    transport = vehicle.get("transport_fee_usd")
    if transport is None:
        pending.append("final Transport fee")
        transport_for_estimate = 0
    else:
        transport_for_estimate = int(transport)
    price = vehicle.get("price_usd")
    if price is None:
        pending.append("listing price")
        price_for_estimate = 0
    else:
        price_for_estimate = int(price)
    otd = estimate_otd(price_for_estimate, transport_for_estimate, buy_box)
    direct_pickup_otd = estimate_otd(price_for_estimate, 0, buy_box)

    decision_tier = "WAIT"
    strength: str | None = None
    reasons = list(failures)
    opportunity_tier: str | None = None
    if failures:
        decision_tier = "EXCLUDE"
    elif price is None or mileage is None:
        decision_tier = "WAIT"
        reasons.append("price or mileage pending")
    elif (
        int(price) >= int(bands["avoid"]["minimum_listing_price_usd"])
        and int(mileage) >= int(bands["avoid"]["minimum_mileage"])
    ):
        decision_tier = "EXCLUDE"
        reasons.append("$35k+ with 40k–50kmi poor-value band")
    elif otd["high"] > float(buy_box["market"]["max_otd_usd"]):
        decision_tier = "WAIT"
        reasons.append("estimated OTD exceeds cap")
    elif _matches_price_mileage_band(
        int(price),
        int(mileage),
        bands.get("ultra_value", bands.get("exceptional_buy")),
    ):
        decision_tier, strength, opportunity_tier = "BUY", "ultra-value", "ULTRA VALUE"
    elif _matches_price_mileage_band(
        int(price),
        int(mileage),
        bands.get("high_priority", bands.get("very_good_buy")),
    ):
        decision_tier, strength, opportunity_tier = "BUY", "high-priority", "HIGH PRIORITY"
    elif _matches_price_mileage_band(int(price), int(mileage), bands.get("buy")):
        decision_tier, opportunity_tier = "BUY", "BUY"
    elif (
        int(price) <= int(bands["fair"]["maximum_listing_price_usd"])
        and int(mileage) < int(bands["fair"]["maximum_mileage"])
    ):
        decision_tier = "FAIR"
    else:
        decision_tier = "WAIT"
        reasons.append("outside current price/mileage Buy Box")

    verification = "FAIL" if failures else "VERIFY FIRST" if pending else "PASS"
    monitor_tier = opportunity_tier or decision_tier
    target = None
    if decision_tier == "WAIT" and price is not None:
        high_priority = bands.get("high_priority", bands.get("very_good_buy"))
        target = int(
            min(
                float(_maximum_band_price(high_priority, int(price))),
                maximum_listing_price(transport_for_estimate, buy_box),
            )
        )
    return {
        "tier": decision_tier,
        "strength": strength,
        "opportunity_tier": opportunity_tier,
        "monitor_tier": monitor_tier,
        "verification": verification,
        "failures": failures,
        "pending": pending,
        "reasons": reasons,
        "otd": otd,
        "direct_pickup_otd": direct_pickup_otd,
        "listing_price_target_usd": target,
    }
