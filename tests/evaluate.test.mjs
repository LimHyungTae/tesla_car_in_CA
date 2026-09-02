import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { classify, estimateOtd, maximumListingPrice } from "../.claude/skills/tesla-buy-box/scripts/evaluate.mjs";

const config = JSON.parse(fs.readFileSync(new URL("../config/buy-box.json", import.meta.url), "utf8"));

function candidate(overrides = {}) {
  return {
    vin: "TESTVIN0000000001",
    available: true,
    model: "Model Y",
    trim: "Long Range AWD",
    year: 2023,
    hardware: "HW4",
    wheel_inches: 19,
    mileage: 30000,
    price_usd: 34500,
    tesla_cpo: true,
    title_status: "clean",
    accident_or_damage: false,
    prior_use: "lease",
    battery_health: "clear",
    transport_fee_usd: 0,
    ...overrides
  };
}

test("OTD and listing ceilings use the configured Foster City assumptions", () => {
  assert.deepEqual(estimateOtd(35200, 0, config), { low: 39100, high: 39300 });
  assert.equal(maximumListingPrice(0, config), 35840);
  assert.equal(maximumListingPrice(500, config), 35340);
  assert.equal(maximumListingPrice(2500, config), 33340);
});

test("Buy Box bands preserve the owner's final thresholds", () => {
  assert.deepEqual(
    [
      classify(candidate({ price_usd: 34000, mileage: 35000 }), config),
      classify(candidate({ price_usd: 35000, mileage: 25000 }), config),
      classify(candidate({ price_usd: 35500, mileage: 25000 }), config),
      classify(candidate({ price_usd: 35500, mileage: 30000 }), config),
      classify(candidate({ price_usd: 35000, mileage: 35000 }), config),
      classify(candidate({ price_usd: 35400, mileage: 32000 }), config)
    ].map(result => [result.tier, result.strength]),
    [
      ["BUY", "ultra-value"],
      ["BUY", "ultra-value"],
      ["BUY", "high-priority"],
      ["BUY", "high-priority"],
      ["BUY", null],
      ["FAIR", null]
    ]
  );
});

test("hard vehicle and history failures cannot be rescued by price", () => {
  assert.equal(classify(candidate({ price_usd: 30000, wheel_inches: 20 }), config).tier, "EXCLUDE");
  assert.equal(classify(candidate({ price_usd: 30000, hardware: "HW3" }), config).tier, "EXCLUDE");
  assert.equal(classify(candidate({ price_usd: 30000, accident_or_damage: true }), config).tier, "EXCLUDE");
  assert.equal(classify(candidate({ price_usd: 30000, prior_use: "rental" }), config).tier, "EXCLUDE");
  assert.equal(classify(candidate({ price_usd: 30000, prior_use: "Commercial Use" }), config).tier, "EXCLUDE");
  assert.equal(classify(candidate({ price_usd: 30000, prior_use: "rental fleet" }), config).tier, "EXCLUDE");
});

test("high-price high-mileage red band is excluded", () => {
  const result = classify(candidate({ price_usd: 35700, mileage: 47548 }), config);
  assert.equal(result.tier, "EXCLUDE");
  assert.match(result.reasons.join(" "), /poor-value/);
});

test("an otherwise suitable over-budget car waits with a target", () => {
  const result = classify(candidate({ price_usd: 36800, mileage: 27544 }), config);
  assert.equal(result.tier, "WAIT");
  assert.equal(result.listing_price_target_usd, 35500);
});

test("unknown SOH and Transport never become an unconditional pass", () => {
  const result = classify(candidate({ battery_health: "unknown", transport_fee_usd: null }), config);
  assert.equal(result.tier, "BUY");
  assert.equal(result.verification, "VERIFY FIRST");
  assert.deepEqual(result.pending.sort(), ["Battery Health/SOH", "final Transport fee"].sort());
});

test("current baseline and shared skill bridge exist", () => {
  assert.equal(fs.existsSync(path.resolve("0902_candidates_v2.html")), true);
  assert.equal(fs.existsSync(path.resolve(".agents/skills/tesla-buy-box/SKILL.md")), true);
  assert.equal(fs.existsSync(path.resolve(".claude/skills/tesla-buy-box/SKILL.md")), true);
});
