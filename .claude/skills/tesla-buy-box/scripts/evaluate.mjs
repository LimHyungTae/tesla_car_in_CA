#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../../..");

export function estimateOtd(price, transport, config) {
  const { sales_tax_rate: tax, estimated_fixed_fees_usd: fees } = config.market;
  return {
    low: (price + transport) * (1 + tax) + fees.low,
    high: (price + transport) * (1 + tax) + fees.high
  };
}

export function maximumListingPrice(transport, config) {
  const { sales_tax_rate: tax, estimated_fixed_fees_usd: fees, max_otd_usd: max } = config.market;
  return (max - fees.high) / (1 + tax) - transport;
}

function normalized(value) {
  return String(value ?? "").trim().toLowerCase();
}

export function classify(candidate, config) {
  const gates = config.vehicle_gates;
  const bands = config.price_mileage_bands;
  const failures = [];
  const pending = [];

  if (candidate.available === false) failures.push("not currently available");
  if (candidate.model !== gates.model) failures.push("wrong model");
  if (!gates.accepted_trims.includes(candidate.trim)) failures.push("wrong trim");
  if (candidate.year < gates.minimum_year) failures.push("model year below minimum");
  if (candidate.hardware !== gates.required_hardware) failures.push("not HW4");
  if (candidate.wheel_inches !== gates.required_wheel_inches) failures.push("not 19-inch wheels");
  if (candidate.mileage >= gates.maximum_mileage_exclusive) failures.push("50,000mi or more");
  if (candidate.tesla_cpo !== true) failures.push("not Tesla CPO");

  if (candidate.title_status == null) pending.push("title status");
  else if (normalized(candidate.title_status) !== "clean") failures.push("title is not clean");

  if (candidate.accident_or_damage == null) pending.push("accident/damage history");
  else if (candidate.accident_or_damage === true) failures.push("reported accident/damage");

  if (candidate.prior_use == null) pending.push("prior use");
  else if (gates.excluded_prior_use.some((value) => normalized(candidate.prior_use).includes(normalized(value)))) failures.push(`excluded prior use: ${candidate.prior_use}`);

  if (candidate.battery_health === "issue") failures.push("Battery Health issue");
  else if (candidate.battery_health !== "clear") pending.push("Battery Health/SOH");

  if (candidate.transport_fee_usd == null) pending.push("final Transport fee");
  const transport = candidate.transport_fee_usd ?? 0;
  const otd = estimateOtd(candidate.price_usd, transport, config);
  const buyBoxPriceTarget = Math.min(
    bands.high_priority.maximum_listing_price_usd,
    maximumListingPrice(transport, config)
  );

  let tier;
  let strength = null;
  const reasons = [...failures];

  if (failures.length) {
    tier = "EXCLUDE";
  } else if (
    candidate.price_usd >= bands.avoid.minimum_listing_price_usd &&
    candidate.mileage >= bands.avoid.minimum_mileage
  ) {
    tier = "EXCLUDE";
    reasons.push("$35k+ with 40k–50kmi poor-value band");
  } else if (otd.high > config.market.max_otd_usd) {
    tier = "WAIT";
    reasons.push("estimated OTD exceeds cap");
  } else if (bands.ultra_value.any_of.some((band) =>
    candidate.price_usd <= band.maximum_listing_price_usd &&
    candidate.mileage <= band.maximum_mileage
  )) {
    tier = "BUY";
    strength = "ultra-value";
  } else if (
    candidate.price_usd <= bands.high_priority.maximum_listing_price_usd &&
    candidate.mileage <= bands.high_priority.maximum_mileage
  ) {
    tier = "BUY";
    strength = "high-priority";
  } else if (
    candidate.price_usd <= bands.buy.maximum_listing_price_usd &&
    candidate.mileage <= bands.buy.maximum_mileage
  ) {
    tier = "BUY";
  } else if (
    candidate.price_usd <= bands.fair.maximum_listing_price_usd &&
    candidate.mileage < bands.fair.maximum_mileage
  ) {
    tier = "FAIR";
  } else {
    tier = "WAIT";
    reasons.push("outside current price/mileage Buy Box");
  }

  return {
    vin: candidate.vin,
    tier,
    strength,
    monitor_tier: strength === "ultra-value" ? "ULTRA VALUE" : strength === "high-priority" ? "HIGH PRIORITY" : tier,
    verification: failures.length ? "FAIL" : pending.length ? "VERIFY FIRST" : "PASS",
    failures,
    pending,
    reasons,
    otd,
    listing_price_target_usd: tier === "WAIT" ? Math.floor(buyBoxPriceTarget) : null
  };
}

function main() {
  const inputPath = path.resolve(process.cwd(), process.argv[2] ?? "data/snapshots/2026-09-02.json");
  const configPath = path.resolve(process.cwd(), process.argv[3] ?? "config/buy-box.json");
  const input = JSON.parse(fs.readFileSync(inputPath, "utf8"));
  const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
  const candidates = Array.isArray(input) ? input : input.candidates;
  const result = candidates.map(candidate => classify(candidate, config));
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
