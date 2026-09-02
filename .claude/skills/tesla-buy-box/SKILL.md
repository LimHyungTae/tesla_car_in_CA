---
name: tesla-buy-box
description: Evaluate, refresh, or maintain the automated used Tesla Model Y monitor in this repository using the owner's Foster City Buy Box, history/SOH/OTD gates, GitHub Actions, and Pages dashboard. Use for inventory searches, VIN assessments, monitor debugging, dashboard changes, dated reports, used financing, or EV incentives; do not use for unrelated vehicles.
---

# Tesla Buy Box

Produce a decision the owner can act on, not a padded Top 5. Start from `PROJECT_STATE.md` and `config/buy-box.json` at the repository root.

## Choose the mode

- For a current inventory refresh or HTML report, read [references/update-workflow.md](references/update-workflow.md) and [references/buy-box.md](references/buy-box.md).
- For one VIN or a comparison supplied by the user, read [references/buy-box.md](references/buy-box.md). Browse only the facts that are missing or time-sensitive.
- For financing or incentives, read the relevant source rules in [references/update-workflow.md](references/update-workflow.md); re-check current primary sources even if a prior report contains an answer.
- For scheduler, crawler, persistence, alert, GitHub Actions, or Pages work, read [references/monitor-operations.md](references/monitor-operations.md) and keep its failure-safety invariants.

## Core decision contract

1. Apply immutable vehicle/history gates before price ranking. Known accident or damage, branded title, excluded prior use, non-HW4, non-CPO, wrong trim/year, 20/21-inch wheels, or 50,000mi and above is `EXCLUDE`.
2. Treat price and OTD as correctable market conditions. A vehicle that otherwise fits but exceeds the target is `WAIT`, with the exact listing-price target needed.
3. Treat missing AutoCheck, prior use, title, Transport, and Battery Health evidence as pending—not as a pass. Add a visible `VERIFY FIRST` modifier. Never call a vehicle an unconditional BUY while a hard-verification item is pending.
4. Never infer battery SOH from rated or displayed range. Request BMS/Battery Health evidence and keep SOH `Pending` until it exists.
5. Classify into exactly one underlying decision tier: `BUY`, `FAIR`, `WAIT`, or `EXCLUDE`. The monitor may promote a BUY opportunity through `BUY` → `HIGH PRIORITY` → `ULTRA VALUE`; use the exact configured thresholds.
6. Use the configured weights only to break ties inside the same tier after hard gates. Missing inputs must stay visible; do not manufacture a precise composite score.
7. Do not force five recommendations. Report zero BUY vehicles when that is the evidence-backed result.

Use `scripts/evaluate.mjs` for deterministic OTD and tier calculations. Its result supports the analysis but does not replace source verification.

## Output rules

- Lead with the number of confirmed and conditional BUY vehicles and the best next action.
- Separate facts, calculated estimates, and unresolved checks.
- Show listing price, mileage, wheel, HW version, CPO status, AutoCheck/title/prior use, SOH status, location, Transport scenario, and OTD range for every actionable candidate.
- Explain why each candidate is BUY, FAIR, WAIT, or EXCLUDE and state the price target for WAIT vehicles.
- Preserve dated reports. Only when an HTML report is requested, create `MMDD_candidates.html`, or the next `_vN` suffix for a same-day revision. Scheduled monitoring updates JSON and the static dashboard instead.
- Update `data/snapshots/YYYY-MM-DD.json` and `PROJECT_STATE.md` whenever producing a new baseline.
- Validate with `python -m pytest -q` and `npm test`; render desktop and mobile HTML when browser tooling is available.

## Safety boundary

Research, calculations, and local report updates are authorized by ordinary refresh requests. Never place an order, pay a deposit or Transport fee, submit financing/prequalification, contact a seller, or reserve a car without a separate explicit instruction for that action.
