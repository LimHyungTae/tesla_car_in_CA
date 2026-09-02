# Tesla Model Y CPO Buy Box

This repository tracks a Foster City, California purchase decision for a used Tesla Model Y. Treat the files as a decision system, not as a generic vehicle-ranking project.

## Source of truth

- Read `PROJECT_STATE.md` first for the current baseline report and snapshot.
- Read `config/buy-box.json` for machine-readable preferences and thresholds.
- Read `config/monitor.json` for scheduler, source-safety, persistence, and dashboard paths.
- Use the repo skill at `.agents/skills/tesla-buy-box/SKILL.md` whenever the user asks to refresh inventory, assess a VIN, compare financing or incentives, or update an HTML report.
- The current report baseline is `0902_candidates_v2.html`. Preserve older dated reports as historical snapshots.

## Non-negotiable behavior

- Re-query current inventory and time-sensitive offers; never copy stale availability, price, APR, incentive, tax, or program status into a new report.
- Use official Tesla and government/utility sources for final claims. A tracker may discover inventory and price history but does not replace Tesla checkout or AutoCheck.
- Apply history, title, prior-use, hardware, wheel, CPO, and battery gates before weighted ranking. A low price never rescues a failed hard gate.
- Never infer battery SOH from displayed range. If no BMS/Battery Health evidence exists, mark SOH as pending and make any buy verdict conditional.
- Distinguish listing price from OTD, include taxable Transport in scenarios, and show the exact observation timestamp in America/Los_Angeles.
- Use the four decision tiers defined in the skill: BUY, FAIR, WAIT, EXCLUDE. Do not force a Top 5 when no vehicle qualifies.
- Do not place an order, pay a deposit, submit a credit application, contact a seller, or reserve a vehicle without an explicit user request for that external action.
- Preserve the last successful inventory on every Tesla source or parser failure; expose the failure through dashboard status instead of replacing inventory with an empty list.

## Deliverables and verification

- For a new date, create `MMDD_candidates.html`; if revising the same date, append `_v2`, `_v3`, and so on. Never overwrite historical reports unless explicitly asked.
- Update `data/snapshots/YYYY-MM-DD.json` and `PROJECT_STATE.md` with the evidence timestamp and baseline filename.
- Keep the report usable on desktop and mobile, make listing/source links clickable, and separate verified facts from assumptions.
- Run `python -m pytest -q` and `npm test` after changing monitor code, rules, snapshots, skills, or reports. Render the dashboard at desktop and mobile widths when browser tooling is available.
