"""Conservative client for Tesla's public inventory v4 endpoint."""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class SourceError(RuntimeError):
    """A complete, retried source request failed."""


class ParserError(SourceError):
    """The source returned data that did not match the documented shape."""


@dataclass(frozen=True)
class FetchResult:
    vehicles: list[dict[str, Any]]
    page_count: int
    reported_total: int | None


def _inventory_query(source: Mapping[str, Any], offset: int) -> dict[str, Any]:
    page_size = int(source.get("page_size", 50))
    radius = int(source.get("radius_miles", source.get("radius", source.get("range", 200))))
    query = {
        "model": source.get("model", "my"),
        "condition": source.get("condition", "used"),
        "arrangeby": source.get("arrangeby", "Price"),
        "order": source.get("order", "asc"),
        "market": source.get("market", "US"),
        "language": source.get("language", "en"),
        "super_region": source.get("super_region", "north america"),
        "PaymentType": source.get("payment_type", "cash"),
        "zip": str(source.get("zip", "94404")),
        "range": radius,
        "lat": float(source.get("latitude", source.get("lat", 37.5538))),
        "lng": float(source.get("longitude", source.get("lng", -122.2711))),
    }
    region = source.get("region")
    if region:
        query["region"] = region
    return {
        "query": query,
        "offset": offset,
        "count": page_size,
        "outsideOffset": 0,
        "outsideSearch": False,
        "isFalconDeliverySelectionEnabled": False,
    }


def _extract_page(payload: Any) -> tuple[list[dict[str, Any]], int | None]:
    if not isinstance(payload, dict):
        raise ParserError("Tesla inventory response is not a JSON object")
    containers = [payload]
    if isinstance(payload.get("data"), dict):
        containers.append(payload["data"])
    results: list[Any] | None = None
    owner: Mapping[str, Any] = payload
    for container in containers:
        for key in ("results", "vehicles", "inventory"):
            if key in container:
                results = container[key]
                owner = container
                break
        if results is not None:
            break
    if not isinstance(results, list):
        raise ParserError("Tesla inventory response has no results list")
    if any(not isinstance(item, dict) for item in results):
        raise ParserError("Tesla inventory results contain a non-object item")
    total: int | None = None
    for container in (owner, payload):
        for key in ("total_matches_found", "totalMatchesFound", "total", "count"):
            value = container.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                total = int(value)
                break
        if total is not None:
            break
    return list(results), total


class TeslaInventoryClient:
    """Fetch inventory with bounded retries and no anti-bot bypass behavior."""

    def __init__(
        self,
        source: Mapping[str, Any],
        *,
        opener: Callable[..., Any] = urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.source = source
        self.opener = opener
        self.sleeper = sleeper

    def _request_page(self, offset: int) -> tuple[list[dict[str, Any]], int | None]:
        base_url = str(self.source["base_url"])
        wrapper = _inventory_query(self.source, offset)
        url = f"{base_url}?{urlencode({'query': json.dumps(wrapper, separators=(',', ':'))})}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": str(
                    self.source.get("user_agent", "tesla-buy-box-monitor/1.0 (+https://github.com/)")
                ),
            },
            method="GET",
        )
        timeout = float(self.source.get("timeout_seconds", 20))
        with self.opener(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            if status in (403, 429) or status >= 500:
                raise HTTPError(url, status, f"HTTP {status}", response.headers, None)
            body = response.read()
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ParserError(f"Tesla inventory returned invalid JSON: {exc}") from exc
        return _extract_page(payload)

    def _request_with_retry(self, offset: int) -> tuple[list[dict[str, Any]], int | None]:
        attempts = max(1, int(self.source.get("maximum_attempts", self.source.get("max_attempts", 3))))
        base_backoff = max(
            0.0,
            float(self.source.get("initial_backoff_seconds", self.source.get("backoff_seconds", 2))),
        )
        last_error: BaseException | None = None
        for attempt in range(1, attempts + 1):
            try:
                return self._request_page(offset)
            except HTTPError as exc:
                last_error = exc
                retriable = exc.code in (403, 408, 429) or exc.code >= 500
                exc.close()
                if not retriable or attempt == attempts:
                    break
            except (ParserError, URLError, TimeoutError, socket.timeout, OSError) as exc:
                last_error = exc
                if attempt == attempts:
                    break
            self.sleeper(base_backoff * (2 ** (attempt - 1)))
        raise SourceError(f"Tesla inventory request failed after {attempts} attempt(s): {last_error}") from last_error

    def fetch(self) -> FetchResult:
        page_size = max(1, int(self.source.get("page_size", 50)))
        max_pages = max(1, int(self.source.get("max_pages", 10)))
        vehicles: list[dict[str, Any]] = []
        reported_total: int | None = None
        for page_index in range(max_pages):
            page, total = self._request_with_retry(page_index * page_size)
            if total is not None:
                reported_total = total
            vehicles.extend(page)
            if len(page) < page_size:
                return FetchResult(vehicles, page_index + 1, reported_total)
            if reported_total is not None and len(vehicles) >= reported_total:
                return FetchResult(vehicles[:reported_total], page_index + 1, reported_total)
        if reported_total is not None and len(vehicles) < reported_total:
            raise ParserError(
                f"Pagination stopped at {len(vehicles)} of {reported_total} reported vehicles"
            )
        return FetchResult(vehicles, max_pages, reported_total)
