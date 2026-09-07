# Buy Box v3

## Hard vehicle and verification gates

The target is a Tesla Certified Pre-Owned Model Y Long Range AWD with:

- model year 2023 or newer;
- HW4;
- 19-inch or 20-inch wheels (19-inch preferred for efficiency, ride comfort, and tire cost);
- white exterior preferred as a soft tie-breaker; other configured neutral colors still pass;
- fewer than 50,000 miles, preferably 35,000 or fewer;
- no reported accident or damage and a clean title;
- no rental, fleet, commercial, taxi, or rideshare use; personal or lease use is acceptable;
- no Battery Health/BMS/thermal-management issue;
- Foster City estimated OTD at or below $40,000.

A known failure in a fixed vehicle/history gate is `EXCLUDE`. Missing history or battery evidence is `VERIFY FIRST`. Price and OTD can change, so an otherwise suitable over-budget vehicle is `WAIT`, not permanently excluded.

## Price and mileage bands

Evaluate in this order after the fixed gates:

1. `ULTRA VALUE`: either (A) listing price at or below $34,000 and mileage at or below 35,000, or (B) listing price at or below $35,000 and mileage at or below 25,000.
2. `HIGH PRIORITY`: listing price at or below $35,500 and mileage at or below 30,000.
3. `BUY`: listing price at or below $35,000 and mileage at or below 35,000.
4. `FAIR`: listing price at or below $35,500 and mileage below 40,000, when none of the stronger BUY bands applies.
5. `EXCLUDE — poor value`: listing price $35,000 or more with 40,000–49,999 miles.
6. `WAIT`: otherwise, including a good low-mileage car whose current listing price or OTD needs to fall.

Every BUY/FAIR verdict still requires OTD at or below $40,000. If a fact needed by a hard gate is unknown, show the underlying tier as conditional and add `VERIFY FIRST`.

## OTD calculation

Use:

```text
OTD low  = (listing price + taxable Transport) × 1.09375 + $600
OTD high = (listing price + taxable Transport) × 1.09375 + $800
```

The fixed-fee band is an estimate; Tesla checkout controls. With the high-fee assumption, the maximum listing prices are:

| Taxable Transport | Maximum listing price for $40,000 OTD |
|---:|---:|
| $0 | $35,840 |
| $500 | $35,340 |
| $1,000 | $34,840 |
| $2,500 | $33,340 |

Always distinguish current-location pickup from moving the vehicle to another delivery center. Do not silently assume a cached Transport value is the buyer's final charge.

## Tie-break priorities

Hard gates are outside the score. Within the same tier use:

- price 30%;
- mileage 25%;
- exterior color preference 15% (White preferred; other configured neutral colors remain eligible);
- remaining Original Basic warranty 10%;
- model year 10%;
- wheel preference 5% (19-inch preferred, but 20-inch remains eligible);
- options 4%;
- pickup location 1%.

Warranty mileage gap is not the actual remaining warranty. The Original Basic warranty is limited by both four years from original delivery and 50,000 total miles. The CPO limited warranty follows according to Tesla's current terms. Do not pay thousands merely for a small Basic-warranty mileage difference when history, SOH, price, and total mileage favor another car.

## Decision examples

- $34,600 / 32,000mi / 19- or 20-inch with all gates passed: `BUY`.
- $34,000 / 35,000mi / 19- or 20-inch with all gates passed: `ULTRA VALUE`.
- $35,000 / 25,000mi / 19- or 20-inch with all gates passed: `ULTRA VALUE`.
- $35,400 / 24,000mi / 19- or 20-inch with all gates passed: `HIGH PRIORITY`.
- $35,400 / 32,000mi / 19- or 20-inch with all gates passed: `FAIR`.
- $36,800 / 27,000mi / 19- or 20-inch: `WAIT`; give the price required for both the Buy Box and OTD.
- $35,700 / 47,000mi: `EXCLUDE — poor value`, even if direct-pickup OTD barely fits.
- Any 21-inch/unsupported-wheel, accident-history, branded-title, or excluded-use vehicle: `EXCLUDE` regardless of price.
