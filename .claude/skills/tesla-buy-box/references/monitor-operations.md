# Automated Monitor Operations

## Architecture and source of truth

- `.github/workflows/tesla-monitor.yml` is the only scheduled workflow. It has schedule and manual triggers, never a push trigger.
- `config/monitor.json` controls cadence, source safety, neutral colors, alert thresholds, and persistence paths.
- `config/buy-box.json` controls every vehicle gate and price/mileage promotion. Do not hard-code competing thresholds in the crawler or dashboard.
- `data/state.json`, `data/inventory.json`, and `data/history.json` are the repository-persisted canonical state. `dashboard/data/` is the publishable projection.
- `tesla_monitor/` owns schedule decisions, conservative source access, normalization, evaluation, diffing, and atomic persistence.
- `dashboard/` must remain a dependency-free static site that works at a GitHub project Pages path.

## Scheduler contract

GitHub wakes the workflow at UTC minutes 07, 22, 37, and 52. Python decides whether a real crawl is due from the latest successful crawl:

- America/Los_Angeles 00:00–04:59: 15 minutes;
- America/Los_Angeles 05:00–23:59: 30 minutes;
- use `zoneinfo.ZoneInfo`, so PDT/PST transitions are based on real instants rather than hand-written UTC offsets;
- a manual run with `force_crawl=true` bypasses only the cadence gate.

Never add a `push` trigger merely to deploy bot-generated data; that creates duplicate runs. Keep workflow concurrency at one non-cancelled `tesla-monitor` group.

## Source and persistence safety

- Use bounded timeouts, retries, exponential backoff, and explicit 403/429 handling.
- Do not add CAPTCHA solving, browser fingerprint evasion, proxy rotation, or any anti-bot bypass.
- Treat malformed, suspiciously empty, or incomplete responses as source failures.
- On source failure, preserve the last successful `data/inventory.json`. Update the public status to `degraded`, or `failed` only when no usable baseline exists, and record the reason.
- Write JSON atomically. Commit generated state only when Git detects changes.
- State is public. Never store cookies, tokens, personal financing data, driver-license data, checkout URLs containing private session data, or other secrets.

## Changes and opportunity promotions

Diff by full VIN. Record new, disappeared, reappeared, price increase/decrease, mileage change, location change, and tier upgrade/downgrade. A price decrease is an alert only at $300 or more.

Opportunity order is:

```text
NONE / WAIT < BUY < HIGH PRIORITY < ULTRA VALUE
```

`ULTRA VALUE` is exactly either:

- price <= $34,000 and mileage <= 35,000; or
- price <= $35,000 and mileage <= 25,000.

All opportunity labels remain conditional when title, accident/damage, prior use, Battery Health/SOH, or buyer-specific Transport evidence is pending.

## Verification before handoff

Run:

```bash
python -m pytest -q
npm test
python -m tesla_monitor.cli --force --now 2026-09-02T00:00:00-07:00
```

For deterministic tests, inject a fixture client; do not make unit tests depend on Tesla availability. Validate the workflow YAML, ensure `dashboard/index.html` is at the artifact root, and render desktop plus mobile layouts. A live source failure is acceptable only if the preserved inventory and degraded/failed status behavior are verified.

To start a production refresh after the workflow is on the default branch, use the GitHub Actions **Run workflow** control and set `force_crawl` deliberately. Do not reserve a vehicle or submit financing as part of a monitor run.
