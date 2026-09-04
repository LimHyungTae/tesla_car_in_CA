# Current project state

- Baseline report: `0902_candidates_v2.html`
- Inventory snapshot: `data/snapshots/2026-09-02.json`
- Inventory observed: 2026-09-02 00:08 PDT
- Source feed last seen: 2026-09-01 23:07 PDT
- Decision model: Buy Box v2
- Current result: 0 confirmed BUY, 3 priority WATCH candidates, 4 known EXCLUDE candidates
- Automated monitor: `.github/workflows/tesla-monitor.yml`
- Live dashboard: `https://limhyungtae.github.io/tesla_car_in_CA/`
- Persisted state: `data/state.json`, `data/inventory.json`, `data/history.json`

Future updates must start from the persisted monitor state, baseline report, `config/buy-box.json`, and `config/monitor.json`, then replace all time-sensitive facts with newly verified data. The latest automated promotion labels are BUY, HIGH PRIORITY, and ULTRA VALUE; missing hard-gate evidence remains VERIFY FIRST.

## Monitor operating status — 2026-09-03

- Last verified/seeded inventory snapshot: `2026-09-02T07:08:00Z` (`2026-09-02 00:08 PDT`), 8 last-known candidates.
- Last production attempt before this fix: `2026-09-03T19:16:14Z` (`2026-09-03 12:16 PDT`), HTTP 403 from Tesla/Akamai. No GitHub-hosted live crawl has succeeded yet.
- The persisted inventory was preserved; its prices and availability are stale and must not be described as current.
- The monitor now stops a 403 after one request, applies a six-hour cooldown, and labels preserved dashboard data as `Last-known`. Other transient failures use bounded retry/backoff.
- Do not add browser fingerprinting, CAPTCHA handling, rotating proxies, or an unlicensed third-party scrape as a workaround. Fresh official-only automation needs a Tesla-permitted network/source.
