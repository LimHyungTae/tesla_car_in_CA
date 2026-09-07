# Current project state

- Baseline report: `0906_candidates.html`
- Latest refresh record: `data/snapshots/2026-09-06.json`
- Last verified inventory snapshot: `data/snapshots/2026-09-02.json`
- Last verified inventory observed: 2026-09-02 00:08 PDT
- Source feed last seen: 2026-09-01 23:07 PDT
- Latest automated refresh attempted: 2026-09-06 21:29 PDT
- Latest separate direct check: 2026-09-06 15:11 PDT
- Source status: degraded; current inventory freshness unavailable
- Decision model: Buy Box v3
- Current result: unavailable because the official source did not return a verifiable inventory
- Last-known reclassification: 0 BUY, 5 WAIT, 3 EXCLUDE; Battery Health/SOH pending for all 8
- Wheel/color preference: 19-inch and 20-inch accepted; 19-inch preferred; White exterior preferred
- Automated monitor: `.github/workflows/tesla-monitor.yml`
- Live dashboard: `https://limhyungtae.github.io/tesla_car_in_CA/`
- Purchase checklist: `how-to-buy.md`
- Persisted state: `data/state.json`, `data/inventory.json`, `data/history.json`

Future updates must start from the persisted monitor state, baseline report, `config/buy-box.json`, and `config/monitor.json`, then replace every time-sensitive fact with newly verified data. The latest automated promotion labels are BUY, HIGH PRIORITY, and ULTRA VALUE; missing hard-gate evidence remains VERIFY FIRST.

## Monitor operating status — 2026-09-06

- The official 94404/200-mile Tesla inventory request was rejected with HTTP 403 in a separate direct check at 2026-09-06 15:11:13 PDT. The latest persisted GitHub Actions attempt was also rejected at 21:29:44 PDT.
- No current price, availability, new/disappeared VIN, or price-change claim can be made from the failed refresh. “No verified current candidate” is not the same as “Tesla has no inventory.”
- The last verified/seeded inventory remains `2026-09-02T07:08:00Z` (`2026-09-02 00:08 PDT`), with 8 preserved last-known records.
- Under Buy Box v3, 20-inch no longer causes exclusion. Last-known `PF864217` moves from EXCLUDE to WAIT; `PF840366` remains EXCLUDE solely because it is in the $35k+/40k–50kmi poor-value band.
- No preserved active record has White exterior. Historical White examples remain price-study references only and are not current recommendations.
- The monitor stops a 403 after one request, applies a six-hour cooldown, and labels preserved dashboard data as `Last-known`. Other transient failures use bounded retry/backoff.
- Do not add browser fingerprinting, CAPTCHA handling, rotating proxies, or an unlicensed third-party scrape. Fresh official-only automation needs a Tesla-permitted network or source.
