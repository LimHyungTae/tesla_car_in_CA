from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

from tesla_monitor.cadence import cadence_minutes, is_due, is_stale, next_due_at, parse_instant
from tesla_monitor.changes import detect_changes
from tesla_monitor.cli import main as cli_main
from tesla_monitor.evaluation import estimate_otd, evaluate_vehicle, normalize_vehicle
from tesla_monitor.monitor import run_monitor
from tesla_monitor.source import FetchResult, SourceError, TeslaInventoryClient


REPO_ROOT = Path(__file__).resolve().parents[1]
BUY_BOX = json.loads((REPO_ROOT / "config" / "buy-box.json").read_text(encoding="utf-8"))


def monitor_config() -> dict:
    return {
        "timezone": "America/Los_Angeles",
        "cadence": {
            "overnight_start_hour": 0,
            "overnight_end_hour_exclusive": 5,
            "overnight_interval_minutes": 15,
            "day_interval_minutes": 30,
            "stale_multiplier": 2,
        },
        "source": {
            "base_url": "https://www.tesla.com/inventory/api/v4/inventory-results",
            "market": "US",
            "language": "en",
            "model": "my",
            "condition": "used",
            "zip": "94404",
            "radius_miles": 200,
            "latitude": 37.5538,
            "longitude": -122.2711,
            "page_size": 50,
            "timeout_seconds": 1,
            "maximum_attempts": 3,
            "initial_backoff_seconds": 0,
        },
        "filters": {
            "neutral_colors": ["Black", "Grey", "Gray", "Midnight Silver Metallic", "White"]
        },
        "changes": {"price_drop_alert_usd": 300},
    }


def prepare_root(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.json").write_text(
        json.dumps(monitor_config()), encoding="utf-8"
    )
    (tmp_path / "config" / "buy-box.json").write_text(
        json.dumps(BUY_BOX), encoding="utf-8"
    )
    return tmp_path


def raw_vehicle(vin: str = "7SAYTEST000000001", **overrides) -> dict:
    record = {
        "VIN": vin,
        "Year": 2023,
        "Model": "my",
        "TrimName": "Long Range All-Wheel Drive",
        "HardwareVersion": "HW4",
        "OptionCodeList": "$WY19B,$STY5S",
        "Price": 35500,
        "Odometer": 25000,
        "City": "Colma",
        "StateProvince": "CA",
        "InventoryType": "Used",
        "VehicleHistory": "CLEAN",
        "CleanTitle": True,
        "PriorUse": "lease",
        "BatteryHealth": "clear",
        "TransportFee": 0,
    }
    record.update(overrides)
    return record


class StaticClient:
    def __init__(self, records):
        self.records = records
        self.calls = 0

    def fetch(self):
        self.calls += 1
        return FetchResult(list(self.records), 1, len(self.records))


class FailingClient:
    def fetch(self):
        raise SourceError("deliberate source failure")


def test_cadence_uses_los_angeles_pdt_and_pst():
    config = monitor_config()
    # 07:05Z is 00:05 PDT: the 15-minute overnight cadence applies.
    pdt_now = parse_instant("2026-09-02T07:05:00Z")
    assert cadence_minutes(pdt_now, config) == 15
    assert is_due(pdt_now, "2026-09-02T06:50:00Z", config)
    assert not is_due(pdt_now, "2026-09-02T06:55:01Z", config)
    # 13:00Z is 05:00 PST: the 30-minute daytime cadence applies.
    pst_now = parse_instant("2026-01-15T13:00:00Z")
    assert cadence_minutes(pst_now, config) == 30
    assert is_due(pst_now, "2026-01-15T12:30:00Z", config)


def test_fall_back_compares_absolute_utc_not_repeated_wall_clock():
    config = monitor_config()
    # 01:55 PDT -> 01:10 PST is 15 real minutes even though wall time moves back.
    assert is_due(
        parse_instant("2026-11-01T09:10:00Z"),
        "2026-11-01T08:55:00Z",
        config,
    )


def test_next_due_accounts_for_midnight_and_five_am_interval_changes():
    config = monitor_config()
    # 04:59 PDT success: daytime interval takes effect, so next due is 05:29.
    assert next_due_at(
        parse_instant("2026-09-02T11:59:00Z"),
        "2026-09-02T11:59:00Z",
        config,
    ) == "2026-09-02T12:29:00Z"
    # 23:59 PDT success: overnight interval makes the next run due after 15m.
    assert next_due_at(
        parse_instant("2026-09-03T06:59:00Z"),
        "2026-09-03T06:59:00Z",
        config,
    ) == "2026-09-03T07:14:00Z"


def test_stale_uses_twice_the_current_cadence_and_rejects_future_state():
    config = monitor_config()
    now = parse_instant("2026-09-02T19:00:00Z")  # noon PDT, 30-minute cadence
    assert not is_stale(now, "2026-09-02T18:00:00Z", config)
    assert is_stale(now, "2026-09-02T17:59:59Z", config)
    assert is_stale(now, "2026-09-02T20:00:00Z", config)


def complete_candidate(**overrides):
    candidate = {
        "available": True,
        "model": "Model Y",
        "trim": "Long Range All-Wheel Drive",
        "year": 2023,
        "hardware": "HW4",
        "wheel_inches": 19,
        "mileage": 25000,
        "price_usd": 35500,
        "tesla_cpo": True,
        "title_status": "clean",
        "accident_or_damage": False,
        "prior_use": "lease",
        "battery_health": "clear",
        "transport_fee_usd": 0,
    }
    candidate.update(overrides)
    return candidate


def test_buy_opportunity_levels_are_buy_strengths():
    cases = [
        (34000, 35000, "ULTRA VALUE"),
        (35000, 25000, "ULTRA VALUE"),
        (35500, 25000, "HIGH PRIORITY"),
        (35500, 30000, "HIGH PRIORITY"),
        (35000, 35000, "BUY"),
    ]
    for price, mileage, expected in cases:
        result = evaluate_vehicle(
            complete_candidate(price_usd=price, mileage=mileage), BUY_BOX
        )
        assert result["tier"] == "BUY"
        assert result["monitor_tier"] == expected
        assert result["verification"] == "PASS"


def test_otd_and_hard_gates_follow_buy_box():
    assert estimate_otd(35200, 0, BUY_BOX) == {"low": 39100.0, "high": 39300.0}
    assert estimate_otd(35200, 2500, BUY_BOX) == {"low": 41834.38, "high": 42034.38}
    assert evaluate_vehicle(complete_candidate(wheel_inches=20), BUY_BOX)["tier"] == "EXCLUDE"
    assert evaluate_vehicle(complete_candidate(hardware="HW3"), BUY_BOX)["tier"] == "EXCLUDE"
    assert evaluate_vehicle(complete_candidate(accident_or_damage=True), BUY_BOX)["tier"] == "EXCLUDE"
    assert evaluate_vehicle(complete_candidate(prior_use="rental"), BUY_BOX)["tier"] == "EXCLUDE"
    for prior_use in ("Commercial Use", "rental fleet", "Fleet vehicle", "rideshare lease"):
        assert evaluate_vehicle(complete_candidate(prior_use=prior_use), BUY_BOX)["tier"] == "EXCLUDE"


def test_history_parser_respects_negation_and_string_booleans():
    clean = normalize_vehicle(
        raw_vehicle(
            VehicleHistory="No accidents or damage reported",
            DamageDisclosure="false",
        ),
        monitor_config()["source"],
    )
    assert clean["accident_or_damage"] is False

    disclosed = normalize_vehicle(
        raw_vehicle(VehicleHistory="CLEAN", DamageDisclosure="true"),
        monitor_config()["source"],
    )
    assert disclosed["accident_or_damage"] is True


def test_unknown_history_soh_and_transport_remain_verify_first():
    result = evaluate_vehicle(
        complete_candidate(
            title_status=None,
            accident_or_damage=None,
            prior_use=None,
            battery_health="unknown",
            transport_fee_usd=None,
        ),
        BUY_BOX,
    )
    assert result["tier"] == "BUY"
    assert result["verification"] == "VERIFY FIRST"
    assert {"title status", "accident/damage history", "prior use", "Battery Health/SOH", "final Transport fee"} <= set(result["pending"])


def test_normalizer_handles_official_case_and_never_infers_soh_from_range():
    vehicle = normalize_vehicle(
        raw_vehicle(
            Range=330,
            ActualRange=300,
            TransportFee=250000,
            HardwareVersion="AI4",
        ),
        monitor_config()["source"],
    )
    assert vehicle["vin"] == "7SAYTEST000000001"
    assert vehicle["hardware"] == "HW4"
    assert vehicle["wheel_inches"] == 19
    assert vehicle["transport_fee_usd"] == 2500
    assert vehicle["battery_health"] == "clear"


def test_change_detection_covers_all_required_transitions():
    previous = [
        {"vin": "A", "price_usd": 36800, "mileage": 27000, "location": "Reno, NV", "monitor_tier": "WAIT"},
        {"vin": "B", "price_usd": 35000, "mileage": 20000, "location": "Colma, CA", "monitor_tier": "ULTRA VALUE", "first_seen_at": "2026-08-01T00:00:00Z", "tesla_url": "https://example.test/B"},
    ]
    current = [
        {"vin": "A", "price_usd": 35400, "mileage": 27100, "location": "Colma, CA", "monitor_tier": "HIGH PRIORITY"},
        {"vin": "C", "price_usd": 35000, "mileage": 24000, "location": "Gilroy, CA", "monitor_tier": "ULTRA VALUE"},
    ]
    events, known, inactive, catalog = detect_changes(
        previous,
        current,
        observed_at="2026-09-02T07:00:00Z",
        known_vins={"A", "B"},
        price_drop_alert_usd=300,
    )
    kinds = {(event["vin"], event["type"]) for event in events}
    assert {("A", "price_decrease"), ("A", "mileage_change"), ("A", "location_change"), ("A", "tier_upgrade"), ("B", "disappeared"), ("C", "new")} <= kinds
    drop = next(event for event in events if event["vin"] == "A" and event["type"] == "price_decrease")
    assert drop["alert"] is True
    assert inactive == {"B"}
    assert known == {"A", "B", "C"}
    disappeared = next(event for event in events if event["vin"] == "B" and event["type"] == "disappeared")
    assert disappeared["before"]["first_seen_at"] == "2026-08-01T00:00:00Z"
    assert disappeared["before"]["tesla_url"] == "https://example.test/B"

    reappeared, _, inactive, _ = detect_changes(
        current,
        current + [previous[1]],
        observed_at="2026-09-02T07:30:00Z",
        known_vins=known,
        inactive_vins=inactive,
        catalog=catalog,
    )
    assert any(event["vin"] == "B" and event["type"] == "reappeared" for event in reappeared)
    assert "B" not in inactive


def test_price_drop_alert_boundary_is_300_dollars():
    previous = [
        {"vin": "DROP300", "price_usd": 35000},
        {"vin": "DROP299", "price_usd": 35000},
    ]
    current = [
        {"vin": "DROP300", "price_usd": 34700},
        {"vin": "DROP299", "price_usd": 34701},
    ]
    events, *_ = detect_changes(
        previous,
        current,
        observed_at="2026-09-02T07:00:00Z",
        price_drop_alert_usd=300,
    )
    alerts = {event["vin"]: event["alert"] for event in events if event["type"] == "price_decrease"}
    assert alerts == {"DROP299": False, "DROP300": True}


def test_success_persists_and_syncs_all_dashboard_files():
    with tempfile.TemporaryDirectory() as directory:
        root = prepare_root(Path(directory))
        result = run_monitor(
            root,
            force=True,
            now="2026-09-02T07:00:00Z",
            client=StaticClient([raw_vehicle()]),
        )
        assert result.status == "success"
        for relative in (
            "data/state.json",
            "data/history.json",
            "data/inventory.json",
            "dashboard/data/status.json",
            "dashboard/data/history.json",
            "dashboard/data/inventory.json",
            "dashboard/data/buy-box.json",
            "dashboard/data/monitor.json",
        ):
            assert (root / relative).exists(), relative
        inventory = json.loads((root / "data/inventory.json").read_text())
        assert inventory["count"] == 1
        assert inventory["source"]["no_price_floor"] is True
        status = json.loads((root / "dashboard/data/status.json").read_text())
        assert status["status"] == "healthy"
        assert status["failure_reason"] is None
        assert status["last_successful_crawl"] == "2026-09-02T07:00:00Z"
        assert status["last_attempted_crawl"] == "2026-09-02T07:00:00Z"
        assert status["current_candidates"] == 1


def test_observation_history_and_catalog_survive_successive_crawls():
    with tempfile.TemporaryDirectory() as directory:
        root = prepare_root(Path(directory))
        first = raw_vehicle(
            Price=35000,
            FirstSeenAt="2026-08-20T12:00:00Z",
            LastSeenAt="2026-09-02T06:59:00Z",
        )
        run_monitor(root, force=True, now="2026-09-02T07:00:00Z", client=StaticClient([first]))
        second = raw_vehicle(Price=34600, Odometer=25100)
        run_monitor(root, force=True, now="2026-09-02T07:30:00Z", client=StaticClient([second]))

        inventory = json.loads((root / "data/inventory.json").read_text())
        vehicle = inventory["vehicles"][0]
        assert vehicle["first_seen_at"] == "2026-09-02T07:00:00Z"
        assert vehicle["source_first_seen_at"] == "2026-08-20T12:00:00Z"
        assert vehicle["last_seen_at"] == "2026-09-02T07:30:00Z"
        assert vehicle["previous_price_usd"] == 35000
        assert vehicle["price_change_usd"] == -400
        state = json.loads((root / "data/state.json").read_text())
        catalog = state["catalog"][vehicle["vin"]]
        assert catalog["exterior"] is None
        assert catalog["interior"] is None
        assert catalog["hardware"] == "HW4"
        assert catalog["tesla_url"].endswith("#overview")
        assert catalog["first_seen_at"] == "2026-09-02T07:00:00Z"


def test_sparse_live_record_keeps_last_known_evidence_and_provenance():
    with tempfile.TemporaryDirectory() as directory:
        root = prepare_root(Path(directory))
        first = raw_vehicle(
            HistorySource="AutoCheck",
            HistoryVerifiedAt="2026-09-01T20:00:00Z",
            BatteryHealth="clear",
            BatteryHealthSource="Tesla service",
            BatteryHealthCheckedAt="2026-09-01T21:00:00Z",
        )
        run_monitor(root, force=True, now="2026-09-02T07:00:00Z", client=StaticClient([first]))
        sparse = raw_vehicle(
            VehicleHistory=None,
            CleanTitle=None,
            PriorUse=None,
            BatteryHealth=None,
        )
        run_monitor(root, force=True, now="2026-09-02T07:30:00Z", client=StaticClient([sparse]))
        vehicle = json.loads((root / "data/inventory.json").read_text())["vehicles"][0]
        assert vehicle["title_status"] == "clean"
        assert vehicle["accident_or_damage"] is False
        assert vehicle["prior_use"] == "lease"
        assert vehicle["history_source"] == "AutoCheck"
        assert vehicle["history_verified_at"] == "2026-09-01T20:00:00Z"
        assert vehicle["history_evidence_status"] == "last_known"
        assert vehicle["battery_health"] == "clear"
        assert vehicle["battery_health_source"] == "Tesla service"
        assert vehicle["battery_evidence_status"] == "last_known"


def test_scope_filters_non_neutral_paint_but_keeps_20_inch_exclusion():
    with tempfile.TemporaryDirectory() as directory:
        root = prepare_root(Path(directory))
        red = raw_vehicle("RED", OptionCodeList="$PPMR,$WY19B,$STY5S")
        grey_twenty = raw_vehicle("GREY20", OptionCodeList="$PMNG,$WY20P,$STY5S")
        run_monitor(
            root,
            force=True,
            now="2026-09-02T07:00:00Z",
            client=StaticClient([red, grey_twenty]),
        )
        inventory = json.loads((root / "data/inventory.json").read_text())
        assert [vehicle["vin"] for vehicle in inventory["vehicles"]] == ["GREY20"]
        assert inventory["vehicles"][0]["tier"] == "EXCLUDE"


def test_cadence_skip_does_not_call_source():
    with tempfile.TemporaryDirectory() as directory:
        root = prepare_root(Path(directory))
        client = StaticClient([raw_vehicle()])
        run_monitor(root, force=True, now="2026-09-02T07:00:00Z", client=client)
        before = {
            relative: (root / relative).read_bytes()
            for relative in (
                "data/state.json",
                "data/history.json",
                "data/inventory.json",
                "dashboard/data/status.json",
                "dashboard/data/history.json",
                "dashboard/data/inventory.json",
            )
        }
        result = run_monitor(root, now="2026-09-02T07:10:00Z", client=client)
        assert result.status == "skipped"
        assert result.attempted is False
        assert client.calls == 1
        for relative, contents in before.items():
            assert (root / relative).read_bytes() == contents


def test_source_failure_and_suspicious_empty_result_never_erase_inventory():
    with tempfile.TemporaryDirectory() as directory:
        root = prepare_root(Path(directory))
        run_monitor(root, force=True, now="2026-09-02T07:00:00Z", client=StaticClient([raw_vehicle()]))
        inventory_path = root / "data/inventory.json"
        before = inventory_path.read_bytes()

        failed = run_monitor(root, force=True, now="2026-09-02T07:30:00Z", client=FailingClient())
        assert failed.status == "source_error"
        assert failed.stale is True
        assert inventory_path.read_bytes() == before
        status = json.loads((root / "dashboard/data/status.json").read_text())
        assert status["status"] == "degraded"
        assert status["failure_reason"] == "deliberate source failure"
        assert status["last_successful_crawl"] == "2026-09-02T07:00:00Z"
        assert status["last_attempted_crawl"] == "2026-09-02T07:30:00Z"
        assert status["current_candidates"] == 1
        assert status["stale"] is True

        empty = run_monitor(root, force=True, now="2026-09-02T08:00:00Z", client=StaticClient([]))
        assert empty.status == "source_error"
        assert inventory_path.read_bytes() == before


def test_first_source_failure_without_baseline_is_failed_not_degraded():
    with tempfile.TemporaryDirectory() as directory:
        root = prepare_root(Path(directory))
        failed = run_monitor(
            root,
            force=True,
            now="2026-09-02T07:00:00Z",
            client=FailingClient(),
        )
        assert failed.status == "source_error"
        status = json.loads((root / "dashboard/data/status.json").read_text())
        assert status["status"] == "failed"
        assert status["failure_reason"] == "deliberate source failure"
        assert status["current_candidates"] == 0


def test_first_empty_source_is_rejected_unless_explicitly_allowed():
    with tempfile.TemporaryDirectory() as directory:
        root = prepare_root(Path(directory))
        failed = run_monitor(
            root,
            force=True,
            now="2026-09-02T07:00:00Z",
            client=StaticClient([]),
        )
        assert failed.status == "source_error"
        assert not (root / "data/inventory.json").exists()
        status = json.loads((root / "dashboard/data/status.json").read_text())
        assert status["status"] == "failed"


def test_seeded_eight_vehicle_baseline_survives_first_live_source_failure():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        shutil.copytree(REPO_ROOT / "config", root / "config")
        (root / "data").mkdir()
        for name in ("state.json", "history.json", "inventory.json"):
            shutil.copy2(REPO_ROOT / "data" / name, root / "data" / name)
        inventory_path = root / "data/inventory.json"
        before = inventory_path.read_bytes()

        failed = run_monitor(
            root,
            force=True,
            now="2026-09-02T07:30:00Z",
            client=FailingClient(),
        )
        assert failed.status == "source_error"
        assert failed.inventory_count == 8
        assert inventory_path.read_bytes() == before
        status = json.loads((root / "dashboard/data/status.json").read_text())
        assert status["status"] == "degraded"
        assert status["current_candidates"] == 8
        state = json.loads((root / "data/state.json").read_text())
        assert len(state["catalog"]) == 12
        assert len(state["inactive_vins"]) == 4


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self.body = body
        self.status = status
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.body


def test_client_retries_429_and_parser_failure_with_bounded_backoff():
    calls = []
    sleeps = []

    def opener(request, timeout):
        calls.append((request.full_url, timeout))
        if len(calls) == 1:
            raise HTTPError(request.full_url, 429, "rate limited", {}, None)
        if len(calls) == 2:
            return FakeResponse(b"not json")
        return FakeResponse(json.dumps({"results": [], "total_matches_found": 0}).encode())

    source = monitor_config()["source"] | {"initial_backoff_seconds": 2}
    result = TeslaInventoryClient(source, opener=opener, sleeper=sleeps.append).fetch()
    assert result.vehicles == []
    assert len(calls) == 3
    assert sleeps == [2, 4]
    # There is deliberately no min-price query parameter.
    assert "minPrice" not in calls[-1][0]


def test_cli_treats_controlled_source_error_as_degraded_success():
    # Use stdlib patching so this test is collected by unittest and pytest.
    from unittest.mock import patch

    from tesla_monitor.monitor import RunResult

    degraded = RunResult(
        "source_error",
        True,
        False,
        "2026-09-02T07:00:00Z",
        5,
        0,
        0,
        True,
        "HTTP 403 after retries",
    )
    stdout, stderr = StringIO(), StringIO()
    with patch("tesla_monitor.cli.run_monitor", return_value=degraded):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            assert cli_main(["--force", "--now", "2026-09-02T00:00:00-07:00"]) == 0
    assert '"status": "source_error"' in stdout.getvalue()
    assert "WARNING" in stderr.getvalue()
    assert "preserved inventory" in stderr.getvalue()


def load_tests(loader, standard_tests, pattern):
    """Let stdlib unittest run the same free-function tests pytest discovers."""

    suite = unittest.TestSuite()
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            suite.addTest(unittest.FunctionTestCase(value))
    return suite
