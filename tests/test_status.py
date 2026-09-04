from __future__ import annotations

from tesla_monitor.storage import public_status_document


def test_public_status_keeps_403_technical_data_out_of_user_copy() -> None:
    raw_error = "Tesla inventory request failed after 3 attempt(s): HTTP Error 403: Forbidden"
    state = {
        "last_status": "source_error",
        "last_error": raw_error,
        "last_error_code": "http_403",
        "last_http_status": 403,
        "last_successful_at": "2026-09-02T07:08:00Z",
        "last_attempt_at": "2026-09-03T19:16:14Z",
        "stale": True,
        "seed_source": "data/snapshots/2026-09-02.json",
    }
    inventory = {
        "count": 8,
        "generated_at": "2026-09-02T07:08:00Z",
        "source": {"seed_snapshot": "data/snapshots/2026-09-02.json"},
        "vehicles": [{}] * 8,
    }

    status = public_status_document(state, inventory)

    assert status["status"] == "degraded"
    assert status["headline"] == "재고 갱신 지연"
    assert "마지막으로 확인된 스냅샷" in status["message"]
    assert "403" not in status["message"]
    assert "Forbidden" not in status["message"]
    assert status["failure_reason"] == raw_error
    assert status["failure_kind"] == "http_403"
    assert status["failure_http_status"] == 403
    assert status["data_mode"] == "last_known"
    assert status["baseline_kind"] == "seed_snapshot"
    assert status["last_verified_snapshot"] == "2026-09-02T07:08:00Z"
    assert status["last_known_candidates"] == 8


def test_public_status_distinguishes_live_data_from_missing_baseline() -> None:
    healthy = public_status_document(
        {
            "last_status": "success",
            "last_successful_at": "2026-09-03T20:00:00Z",
            "last_attempt_at": "2026-09-03T20:00:00Z",
            "stale": False,
            "seed_source": "data/snapshots/2026-09-02.json",
        },
        {
            "count": 1,
            "source_successful_at": "2026-09-03T20:00:00Z",
            "vehicles": [{}],
        },
    )
    assert healthy["status"] == "healthy"
    assert healthy["data_mode"] == "live"
    assert healthy["baseline_kind"] == "live_crawl"
    assert healthy["health_label"] == "SOURCE HEALTHY"
    assert healthy["failure_reason"] is None

    unavailable = public_status_document(
        {
            "last_status": "source_error",
            "last_error": "HTTP Error 429: Too Many Requests",
            "last_error_code": "http_429",
            "last_http_status": 429,
            "last_successful_at": None,
            "stale": True,
        },
        {"count": 0, "vehicles": []},
    )
    assert unavailable["status"] == "failed"
    assert unavailable["data_mode"] == "unavailable"
    assert unavailable["baseline_kind"] == "none"
    assert unavailable["failure_kind"] == "http_429"
    assert unavailable["failure_http_status"] == 429
    assert "429" not in unavailable["message"]


def test_typed_source_error_metadata_wins_over_legacy_message_parsing() -> None:
    status = public_status_document(
        {
            "last_status": "source_error",
            "last_error": "legacy wrapper mentioned HTTP Error 403: Forbidden",
            "last_error_code": "timeout",
            "last_http_status": None,
            "last_successful_at": "2026-09-03T20:00:00Z",
            "stale": True,
        },
        {
            "count": 1,
            "source_successful_at": "2026-09-03T20:00:00Z",
            "vehicles": [{}],
        },
    )
    assert status["failure_kind"] == "timeout"
    assert status["failure_http_status"] is None
    assert "자동 요청을 거부" not in status["message"]
