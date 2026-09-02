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
