const PATHS = {
  inventory: "./data/inventory.json",
  history: "./data/history.json",
  status: "./data/status.json",
  buyBox: "./data/buy-box.json",
  monitor: "./data/monitor.json",
  fallback: "./data/dashboard.json",
};

const REPOSITORY_BLOB_BASE = "https://github.com/LimHyungTae/tesla_car_in_CA/blob/main/";

const TIER_ORDER = { BUY: 0, FAIR: 1, WAIT: 2, EXCLUDE: 3 };
const $ = (id) => document.getElementById(id);

function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined && content !== null) node.textContent = String(content);
  return node;
}

function firstDefined(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

function get(object, ...paths) {
  for (const path of paths) {
    const value = String(path)
      .split(".")
      .reduce((cursor, part) => (cursor == null ? undefined : cursor[part]), object);
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return undefined;
}

function number(value) {
  if (value === undefined || value === null || value === "") return null;
  const parsed = Number(String(value).replace(/[^0-9.-]/g, ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function boolean(value) {
  if (typeof value === "boolean") return value;
  if (value === 1 || value === "1" || String(value).toLowerCase() === "true") return true;
  if (value === 0 || value === "0" || String(value).toLowerCase() === "false") return false;
  return null;
}

function stringList(value) {
  if (Array.isArray(value)) return value.flatMap(stringList).filter(Boolean);
  if (value === undefined || value === null || value === "") return [];
  if (typeof value === "object") return [];
  return [String(value)];
}

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function timestamp(value) {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

function validTier(value) {
  const tier = String(value || "").toUpperCase().replace(/\s+/g, "_");
  if (tier.includes("EXCLUDE")) return "EXCLUDE";
  if (tier.includes("WAIT") || tier.includes("WATCH") || tier.includes("HOLD")) return "WAIT";
  if (tier.includes("FAIR")) return "FAIR";
  if (tier.includes("BUY")) return "BUY";
  return null;
}

function normalizeMarket(config, inventory) {
  const market = get(config, "market") || {};
  const sourceMarket = get(inventory, "market") || {};
  const normalized = {
    taxRate: number(firstDefined(market.sales_tax_rate, sourceMarket.sales_tax_rate)),
    fixedFeeLow: number(firstDefined(market.estimated_fixed_fees_usd?.low, sourceMarket.estimated_fixed_fees_usd?.low)),
    fixedFeeHigh: number(firstDefined(market.estimated_fixed_fees_usd?.high, sourceMarket.estimated_fixed_fees_usd?.high)),
    maxOtd: number(firstDefined(market.max_otd_usd, sourceMarket.max_otd_usd)),
    zip: firstDefined(market.zip, sourceMarket.zip),
  };
  if ([normalized.taxRate, normalized.fixedFeeLow, normalized.fixedFeeHigh, normalized.maxOtd].some((value) => value === null) || !normalized.zip) {
    throw new Error("dashboard/data/buy-box.json의 Foster City OTD 설정이 불완전합니다.");
  }
  normalized.zip = String(normalized.zip);
  return normalized;
}

function calculateOtd(price, transport, market) {
  if (price === null) return { low: null, high: null };
  const taxableTransport = transport ?? 0;
  const subtotal = (price + taxableTransport) * (1 + market.taxRate);
  return {
    low: Math.round(subtotal + market.fixedFeeLow),
    high: Math.round(subtotal + market.fixedFeeHigh),
  };
}

function deriveDecision(vehicle, market, buyBox, explicit = {}) {
  const failures = [...(explicit.failures || [])];
  const pending = [...(explicit.pending || [])];
  const reasons = [...(explicit.reasons || [])];
  const gates = buyBox.vehicle_gates || {};
  const bands = buyBox.price_mileage_bands || {};
  const trim = String(vehicle.trim || "").toLowerCase();
  const hardware = String(vehicle.hardware || "").toUpperCase();
  const priorUse = String(vehicle.priorUse || "").toLowerCase();

  if (vehicle.year === null) pending.push("model year");
  else if (vehicle.year < Number(gates.minimum_year)) failures.push(`${gates.minimum_year}년 이후 연식이 아님`);
  if (!vehicle.model) pending.push("model");
  else if (vehicle.model !== gates.model) failures.push(`${gates.model}가 아님`);
  if (!vehicle.trim) pending.push("exact trim");
  else if (!(gates.accepted_trims || []).map((value) => String(value).toLowerCase()).includes(trim)) failures.push("Long Range AWD가 아님");
  if (!vehicle.hardware) pending.push(gates.required_hardware || "hardware");
  else if (hardware !== String(gates.required_hardware || "").toUpperCase()) failures.push(`${gates.required_hardware}가 아님`);
  if (vehicle.wheels === null) pending.push("wheel size");
  else if (vehicle.wheels !== Number(gates.required_wheel_inches)) failures.push(`${gates.required_wheel_inches}인치 휠 gate 실패`);
  if (vehicle.miles === null) pending.push("mileage");
  else if (vehicle.miles >= Number(gates.maximum_mileage_exclusive)) failures.push(`${Number(gates.maximum_mileage_exclusive).toLocaleString("en-US")}mi 미만 gate 실패`);
  if (vehicle.teslaCpo === null) pending.push("Tesla CPO status");
  else if (vehicle.teslaCpo === false) failures.push("Tesla CPO가 아님");
  if (vehicle.titleStatus && !String(vehicle.titleStatus).toLowerCase().includes("clean")) failures.push("clean title gate 실패");
  if (vehicle.accident === true) failures.push("사고·damage 이력 gate 실패");
  if ((gates.excluded_prior_use || []).some((term) => priorUse.includes(String(term).toLowerCase()))) failures.push("제외 prior use 이력");
  if (vehicle.price !== null && vehicle.miles !== null && vehicle.price >= Number(bands.avoid?.minimum_listing_price_usd) && vehicle.miles >= Number(bands.avoid?.minimum_mileage)) failures.push("고가·고마일 poor-value band");

  if (!vehicle.titleStatus) pending.push("title status");
  if (vehicle.accident === null) pending.push("사고·damage 이력");
  if (!vehicle.priorUse) pending.push("prior use");
  if (!vehicle.batteryHealth || ["unknown", "pending", "unavailable"].includes(String(vehicle.batteryHealth).toLowerCase())) pending.push("Battery Health / SOH");
  if (vehicle.transport === null) pending.push("최종 Transport");

  const bandMatch = (band) => Boolean(
    band && vehicle.price !== null && vehicle.miles !== null &&
    vehicle.price <= Number(band.maximum_listing_price_usd) &&
    vehicle.miles <= Number(band.maximum_mileage)
  );
  let tier = failures.length ? "EXCLUDE" : explicit.tier;
  let monitorTier = String(vehicle.monitorTier || "");
  if (!tier) {
    if (failures.length) tier = "EXCLUDE";
    else if (vehicle.price === null || vehicle.miles === null) tier = "WAIT";
    else if (vehicle.otd.high > market.maxOtd) tier = "WAIT";
    else if ((bands.ultra_value?.any_of || []).some(bandMatch)) [tier, monitorTier] = ["BUY", "ULTRA VALUE"];
    else if (bandMatch(bands.high_priority)) [tier, monitorTier] = ["BUY", "HIGH PRIORITY"];
    else if (bandMatch(bands.buy)) [tier, monitorTier] = ["BUY", "BUY"];
    else if (
      bands.fair && vehicle.price !== null && vehicle.miles !== null &&
      vehicle.price <= Number(bands.fair.maximum_listing_price_usd) &&
      vehicle.miles < Number(bands.fair.maximum_mileage)
    ) [tier, monitorTier] = ["FAIR", "FAIR"];
    else tier = "WAIT";
  }
  if (!monitorTier) monitorTier = tier;

  const cleanFailures = unique(failures);
  const cleanPending = unique(pending);
  const verification = cleanFailures.length
    ? "FAIL"
    : cleanPending.length
      ? "VERIFY FIRST"
      : String(explicit.verification || "PASS").toUpperCase();
  if (!reasons.length && tier === "WAIT" && vehicle.otd.high !== null && vehicle.otd.high > market.maxOtd) {
    reasons.push(`현재 $0 Transport OTD 상단이 ${formatCurrency(market.maxOtd)} cap을 초과`);
  }

  return {
    tier,
    monitorTier,
    verification,
    failures: cleanFailures,
    pending: cleanPending,
    reasons: unique(reasons),
    targetPrice: explicit.targetPrice ?? null,
    targetLabel: explicit.targetLabel || "BUY 목표가",
  };
}

function normalizeVehicle(raw, market, options = {}) {
  const classificationSource = get(raw, "classification", "decision", "evaluation") || {};
  const classificationObject = typeof classificationSource === "object" ? classificationSource : {};
  const vin = String(firstDefined(get(raw, "vin", "VIN", "vehicle_vin", "vehicleVin"), "미확인"));
  const price = number(firstDefined(get(raw, "price_usd", "priceUsd", "price", "listing_price_usd", "listingPrice"), get(raw, "last_observed_price_usd")));
  const firstPrice = number(get(raw, "first_observed_price_usd", "firstSeenPriceUsd", "tracking.first_price_usd", "changes.first_price_usd"));
  const previousPrice = number(get(raw, "previous_price_usd", "previous_snapshot_price_usd", "previousPriceUsd", "changes.previous_price_usd", "changes.price.previous"));
  const explicitDelta = number(get(raw, "price_change_usd", "priceChangeUsd", "changes.price_change_usd", "changes.price.delta", "change.price_usd"));
  const delta = explicitDelta ?? (firstPrice !== null && price !== null ? price - firstPrice : previousPrice !== null && price !== null ? price - previousPrice : null);
  const transport = number(get(raw, "transport_fee_usd", "transportFeeUsd", "transport", "checkout.transport_fee_usd"));
  const modelValue = firstDefined(get(raw, "model", "vehicle.model"), null);
  const trimValue = firstDefined(get(raw, "trim", "variant", "vehicle.trim"), null);
  const hardwareValue = firstDefined(get(raw, "hardware", "hardware_version", "hardwareVersion", "autopilot_hardware"), null);
  const explicitOtd = get(raw, "otd", "foster_city_otd", "fosterCityOtd", "evaluation.otd", "evaluation.direct_pickup_otd", "classification.otd") || {};
  const calculatedOtd = calculateOtd(price, transport, market);
  const otd = {
    low: number(firstDefined(get(explicitOtd, "low", "min", "low_usd", "estimated_low_usd"), get(raw, "otd_low_usd"))) ?? calculatedOtd.low,
    high: number(firstDefined(get(explicitOtd, "high", "max", "high_usd", "estimated_high_usd"), get(raw, "otd_high_usd"))) ?? calculatedOtd.high,
    transportAssumption: number(firstDefined(get(explicitOtd, "transport_assumption_usd", "transport_usd"), transport)) ?? 0,
  };

  const vehicle = {
    raw,
    vin,
    shortVin: vin.length > 8 ? vin.slice(-8) : vin,
    available: boolean(firstDefined(get(raw, "available", "is_available", "isAvailable", "active"), !options.gone)) !== false,
    gone: options.gone === true,
    model: modelValue === null ? null : String(modelValue),
    trim: trimValue === null ? null : String(trimValue),
    year: number(get(raw, "year", "model_year", "modelYear")),
    hardware: hardwareValue === null ? null : String(hardwareValue),
    wheels: number(get(raw, "wheel_inches", "wheelInches", "wheels_inches", "wheel_size", "wheels")),
    miles: number(firstDefined(get(raw, "mileage", "miles", "odometer_miles", "odometer"), get(raw, "last_observed_mileage"))),
    price,
    firstPrice,
    previousPrice,
    priceDelta: delta,
    priceChangeBasis: String(firstDefined(get(raw, "price_change_basis", "priceChangeBasis"), firstPrice !== null ? "first_seen" : previousPrice !== null ? "previous_snapshot" : "unknown")),
    location: String(firstDefined(get(raw, "location", "delivery_location", "metro", "store"), "미확인")),
    exterior: String(firstDefined(get(raw, "exterior", "exterior_color", "exteriorColor", "paint"), "미확인")),
    interior: String(firstDefined(get(raw, "interior", "interior_color", "interiorColor"), "미확인")),
    teslaCpo: boolean(firstDefined(get(raw, "tesla_cpo", "teslaCpo", "cpo"), null)),
    autocheckScore: number(get(raw, "autocheck_score", "autoCheckScore", "history.autocheck_score")),
    titleStatus: firstDefined(get(raw, "title_status", "titleStatus", "history.title_status"), null),
    accident: boolean(firstDefined(get(raw, "accident_or_damage", "accidentOrDamage", "history.accident_or_damage", "has_accident"), null)),
    accidentDate: firstDefined(get(raw, "accident_date", "accidentDate", "history.accident_date"), null),
    priorUse: firstDefined(get(raw, "prior_use", "priorUse", "history.prior_use"), null),
    batteryHealth: firstDefined(get(raw, "battery_health", "batteryHealth", "soh", "battery.soh"), null),
    transport,
    cachedTransport: number(get(raw, "cached_transfer_fee_usd", "cachedTransportFeeUsd", "cached_transport_fee_usd")),
    otd,
    firstSeen: timestamp(firstDefined(get(raw, "first_seen_at", "firstSeenAt", "first_seen", "source_first_seen_at", "observed.first", "tracking.first_seen_at"), options.defaultFirstSeen)),
    lastSeen: timestamp(firstDefined(get(raw, "last_seen_at", "lastSeenAt", "last_seen", "source_last_seen_at", "observed.last", "tracking.last_seen_at"), options.defaultLastSeen)),
    isNew: boolean(firstDefined(get(raw, "is_new_since_previous_snapshot", "isNewSincePreviousSnapshot", "is_new", "changes.is_new"), false)) === true,
    priorityRank: number(firstDefined(get(raw, "priority_rank", "priorityRank", "classification.priority_rank", "decision.rank"), null)),
    monitorTier: String(firstDefined(get(raw, "monitor_tier", "monitorTier", "evaluation.monitor_tier", "evaluation.opportunity_tier", "opportunity_tier"), "" )).toUpperCase(),
    highPriority: false,
    teslaUrl: String(firstDefined(get(raw, "tesla_url", "teslaUrl", "url"), vin !== "미확인" ? `https://www.tesla.com/my/order/${encodeURIComponent(vin)}?titleStatus=used&redirect=no#overview` : "https://www.tesla.com/inventory/used/my")),
  };

  const explicit = {
    tier: options.gone ? "EXCLUDE" : validTier(typeof classificationSource === "string" ? classificationSource : firstDefined(classificationObject.tier, classificationObject.classification, classificationObject.decision)),
    verification: options.gone ? "FAIL" : firstDefined(classificationObject.verification, classificationObject.verification_status, classificationObject.gate_status),
    failures: unique([
      ...(options.gone ? ["현재 활성 재고에서 이탈"] : []),
      ...stringList(firstDefined(classificationObject.failures, classificationObject.failed_gates)),
    ]),
    pending: stringList(firstDefined(classificationObject.pending, classificationObject.pending_gates, classificationObject.verify)),
    reasons: stringList(firstDefined(classificationObject.reasons, classificationObject.reason, classificationObject.notes)),
    targetPrice: number(firstDefined(classificationObject.listing_price_target_usd, classificationObject.target_price_usd, classificationObject.targetPriceUsd, get(raw, "target_price_usd"))),
    targetLabel: firstDefined(classificationObject.target_label, classificationObject.targetLabel),
  };
  vehicle.decision = deriveDecision(vehicle, market, options.buyBox || {}, explicit);
  if (!vehicle.monitorTier) vehicle.monitorTier = vehicle.decision.monitorTier;
  vehicle.highPriority = ["HIGH PRIORITY", "ULTRA VALUE"].includes(vehicle.monitorTier);
  return vehicle;
}

function normalizeInventory(raw, config) {
  const market = normalizeMarket(config || {}, raw || {});
  const candidates = firstDefined(get(raw, "candidates"), get(raw, "active"), get(raw, "vehicles"), get(raw, "inventory"), []);
  const defaultLastSeen = firstDefined(
    get(raw, "source_successful_at", "sourceSuccessfulAt"),
    get(raw, "source_feed_last_seen_at", "sourceFeedLastSeenAt"),
    get(raw, "generated_at", "generatedAt"),
    get(raw, "snapshot_at", "snapshotAt"),
  );
  return {
    market,
    snapshotAt: timestamp(firstDefined(get(raw, "snapshot_at", "snapshotAt", "generated_at", "generatedAt"), defaultLastSeen)),
    sourceFeedLastSeenAt: timestamp(defaultLastSeen),
    sourceSuccessfulAt: timestamp(firstDefined(get(raw, "source_successful_at", "sourceSuccessfulAt"), defaultLastSeen)),
    sourceName: String(firstDefined(get(raw, "source.name"), get(raw, "source"), "Tesla inventory source")),
    previousSnapshotAt: timestamp(get(raw, "previous_snapshot_at", "previousSnapshotAt")),
    notes: stringList(get(raw, "notes")),
    vehicles: Array.isArray(candidates) ? candidates.map((candidate) => normalizeVehicle(candidate, market, { defaultLastSeen, buyBox: config })) : [],
  };
}

function normalizeHistory(raw, inventory, buyBox, monitorConfig) {
  const goneSource = firstDefined(get(raw, "disappeared"), get(raw, "gone"), get(raw, "unavailable"), []);
  const historySource = firstDefined(get(raw, "snapshots"), get(raw, "history"), get(raw, "timeline"), []);
  const runSource = Array.isArray(get(raw, "runs")) ? get(raw, "runs") : [];
  const eventSource = Array.isArray(get(raw, "events")) ? get(raw, "events") : [];
  const eventContract = Array.isArray(get(raw, "events"));

  const runs = runSource.map((entry) => ({
    at: timestamp(firstDefined(get(entry, "observed_at", "snapshot_at", "date", "at"), null)),
    status: String(firstDefined(get(entry, "status"), "unknown")),
    title: String(firstDefined(get(entry, "details.title"), `Crawler ${String(firstDefined(get(entry, "status"), "run")).replaceAll("_", " ")}`)),
    note: String(firstDefined(get(entry, "details.note", "error", "reason"), get(entry, "status") === "success" ? "Tesla source crawl completed." : "Crawler execution record.")),
    active: number(firstDefined(get(entry, "details.active_count"), get(entry, "inventory_count"), get(entry, "inventory_count_preserved"))),
    priority: number(get(entry, "details.high_priority_count")),
    buy: number(get(entry, "details.buy_count")),
    fresh: number(get(entry, "details.new_count")),
    drops: number(get(entry, "details.price_drop_count")),
    gone: number(get(entry, "details.disappeared_count")),
    events: number(get(entry, "event_count")),
    alerts: number(get(entry, "alert_count")),
    model: firstDefined(get(entry, "details.decision_model"), "monitor run"),
    reportUrl: firstDefined(get(entry, "details.report_url"), null),
    kind: "run",
  }));

  const events = eventSource.map((entry) => {
    const beforeObject = get(entry, "before") && typeof get(entry, "before") === "object" ? get(entry, "before") : null;
    const afterObject = get(entry, "after") && typeof get(entry, "after") === "object" ? get(entry, "after") : null;
    const beforePrice = number(firstDefined(beforeObject?.price_usd, get(entry, "before")));
    const afterPrice = number(firstDefined(afterObject?.price_usd, get(entry, "after")));
    return {
      raw: entry,
      at: timestamp(get(entry, "observed_at", "at", "timestamp")),
      type: String(firstDefined(get(entry, "type"), "unknown")),
      vin: String(firstDefined(get(entry, "vin"), "미확인")),
      alert: boolean(get(entry, "alert")) === true,
      before: get(entry, "before"),
      after: get(entry, "after"),
      beforePrice,
      afterPrice,
      delta: number(firstDefined(get(entry, "details.delta_usd", "delta_usd"), beforePrice !== null && afterPrice !== null ? afterPrice - beforePrice : null)),
    };
  });

  const latestSuccessfulRun = [...runs].reverse().find((run) => run.status === "success");
  const newestEventAt = events.reduce((latest, event) => {
    if (!event.at) return latest;
    return !latest || new Date(event.at) > new Date(latest) ? event.at : latest;
  }, null);
  const latestChangeAt = timestamp(firstDefined(latestSuccessfulRun?.at, inventory.sourceSuccessfulAt, newestEventAt));
  const inLatestChangeSet = (event) => Boolean(event.at && latestChangeAt && new Date(event.at).getTime() === new Date(latestChangeAt).getTime());
  const latestEvents = events.filter(inLatestChangeSet);
  const newEvents = latestEvents.filter((event) => event.type === "new" || event.type === "reappeared");
  const disappearedEvents = latestEvents.filter((event) => event.type === "disappeared" && event.before && typeof event.before === "object");
  const priceDropThreshold = number(get(monitorConfig, "changes.price_drop_alert_usd"));
  const disappearedLimit = number(get(monitorConfig, "changes.recently_disappeared_limit"));
  const priceHistoryLimit = number(get(monitorConfig, "changes.price_history_limit"));
  if ([priceDropThreshold, disappearedLimit, priceHistoryLimit].some((value) => value === null)) {
    throw new Error("dashboard/data/monitor.json의 change/history 설정이 불완전합니다.");
  }
  const configuredPriceDropEvents = latestEvents.filter((event) => event.type === "price_decrease" && (event.alert || (event.delta !== null && event.delta <= -priceDropThreshold)));
  if (latestSuccessfulRun) {
    latestSuccessfulRun.active = inventory.vehicles.filter((vehicle) => vehicle.available && !vehicle.gone).length;
    latestSuccessfulRun.priority = inventory.vehicles.filter((vehicle) => vehicle.available && vehicle.highPriority).length;
    latestSuccessfulRun.buy = inventory.vehicles.filter((vehicle) => vehicle.available && vehicle.decision.tier === "BUY").length;
    latestSuccessfulRun.fresh = newEvents.length;
    latestSuccessfulRun.drops = configuredPriceDropEvents.length;
    latestSuccessfulRun.gone = disappearedEvents.length;
  }

  const backendGone = disappearedEvents.map((event) => normalizeVehicle(event.before, inventory.market, {
    gone: true,
    defaultLastSeen: event.at,
    buyBox,
  })).slice(0, disappearedLimit);
  const legacyGone = Array.isArray(goneSource)
    ? goneSource.map((vehicle) => normalizeVehicle(vehicle, inventory.market, {
        gone: true,
        defaultLastSeen: get(vehicle, "last_seen_at", "lastSeenAt"),
        buyBox,
      })).slice(0, disappearedLimit)
    : [];

  const priceTimeline = events
    .filter((event) => ["price_decrease", "price_increase"].includes(event.type))
    .slice(-priceHistoryLimit)
    .map((event) => {
      const shortVin = event.vin.length > 8 ? event.vin.slice(-8) : event.vin;
      const direction = event.type === "price_decrease" ? "인하" : "인상";
      const valuesKnown = event.beforePrice !== null && event.afterPrice !== null;
      return {
        at: event.at,
        title: `${shortVin} 가격 ${direction}`,
        note: valuesKnown
          ? `${formatCurrency(event.beforePrice)} → ${formatCurrency(event.afterPrice)} (${event.delta > 0 ? "+" : ""}${formatCurrency(event.delta)})`
          : `${event.vin}의 가격 변경 이벤트`,
        active: null,
        priority: null,
        buy: null,
        fresh: null,
        drops: null,
        gone: null,
        events: null,
        alerts: event.alert ? 1 : 0,
        model: event.type,
        reportUrl: null,
        kind: "price",
      };
    });

  const legacyTimeline = Array.isArray(historySource)
    ? historySource.map((entry) => ({
        at: timestamp(firstDefined(get(entry, "snapshot_at", "snapshotAt", "date", "at"), null)),
        title: String(firstDefined(get(entry, "title", "label"), "Inventory snapshot")),
        note: String(firstDefined(get(entry, "note", "summary", "message"), "저장된 관찰 시점입니다.")),
        active: number(get(entry, "active_count", "activeCount")),
        priority: number(get(entry, "high_priority_count", "priority_count", "priorityCount")),
        buy: number(get(entry, "buy_count", "buyCount")),
        fresh: number(get(entry, "new_count", "newCount")),
        drops: number(get(entry, "price_drop_count", "priceDropCount")),
        gone: number(get(entry, "disappeared_count", "gone_count", "goneCount")),
        events: null,
        alerts: null,
        model: firstDefined(get(entry, "decision_model", "decisionModel"), null),
        reportUrl: firstDefined(get(entry, "report_url", "reportUrl"), null),
        kind: "snapshot",
      }))
    : [];

  return {
    eventContract,
    latestChangeAt,
    newEvents,
    priceDropEvents: configuredPriceDropEvents,
    priceDropThreshold,
    gone: eventContract ? backendGone : legacyGone,
    snapshots: eventContract ? [...priceTimeline, ...runs.slice(-20)] : legacyTimeline,
  };
}

async function fetchJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

async function loadData() {
  const [inventoryResult, historyResult, statusResult, buyBoxResult, monitorResult] = await Promise.allSettled([
    fetchJson(PATHS.inventory),
    fetchJson(PATHS.history),
    fetchJson(PATHS.status),
    fetchJson(PATHS.buyBox),
    fetchJson(PATHS.monitor),
  ]);

  const warnings = [];
  let inventoryRaw = inventoryResult.status === "fulfilled" ? inventoryResult.value : null;
  let source = "canonical";
  if (!inventoryRaw) {
    warnings.push("inventory.json을 읽지 못해 fallback 데이터를 확인했습니다.");
    for (const fallbackPath of [PATHS.fallback]) {
      try {
        inventoryRaw = await fetchJson(fallbackPath);
        source = fallbackPath;
        break;
      } catch (_error) {
        // Try the next static fallback.
      }
    }
  }
  if (!inventoryRaw) throw new Error("활성 재고 JSON을 불러오지 못했습니다.");
  if (buyBoxResult.status !== "fulfilled") throw new Error("Buy Box config를 불러오지 못했습니다.");
  if (monitorResult.status !== "fulfilled") throw new Error("Monitor config를 불러오지 못했습니다.");
  if (historyResult.status !== "fulfilled") warnings.push("history.json을 읽지 못해 사라진 차량과 타임라인이 제한됩니다.");
  if (statusResult.status !== "fulfilled") warnings.push("status.json을 읽지 못해 재고 시각만으로 상태를 표시합니다.");

  const inventory = normalizeInventory(inventoryRaw, buyBoxResult.value);
  const history = normalizeHistory(
    historyResult.status === "fulfilled" ? historyResult.value : {},
    inventory,
    buyBoxResult.value,
    monitorResult.value,
  );
  const status = statusResult.status === "fulfilled" ? statusResult.value : {};
  return { inventory, history, status, warnings, source };
}

function formatCurrency(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "미확인";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(Number(value));
}

function formatMiles(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "미확인";
  return `${new Intl.NumberFormat("en-US").format(Number(value))} mi`;
}

function formatDate(value, includeTime = true) {
  if (!value) return "미확인";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "미확인";
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "America/Los_Angeles",
    year: "numeric",
    month: "short",
    day: "numeric",
    ...(includeTime ? { hour: "2-digit", minute: "2-digit", hour12: false } : {}),
  }).format(date);
}

function reportUrl(value) {
  if (!value) return null;
  const url = String(value);
  if (/^https:\/\//i.test(url)) return url;
  const filename = url.split("/").filter(Boolean).pop();
  return filename ? `${REPOSITORY_BLOB_BASE}${encodeURIComponent(filename)}` : null;
}

function colorValue(name) {
  const color = String(name || "").toLowerCase();
  if (color.includes("black")) return "#24272c";
  if (color.includes("white")) return "#f7f7f3";
  if (color.includes("grey") || color.includes("gray") || color.includes("silver")) return "#777d84";
  if (color.includes("blue")) return "#225a9d";
  if (color.includes("red")) return "#b9232c";
  return "#b9bdc4";
}

function detail(label, value) {
  const wrapper = element("div", "detail");
  const term = element("dt", "", label);
  const description = element("dd", "", value || "미확인");
  wrapper.append(term, description);
  return wrapper;
}

function emptyState(title, copy, error = false) {
  const wrapper = element("div", `empty-state${error ? " empty-state--error" : ""}`);
  wrapper.append(
    element("span", "empty-state__mark", error ? "!" : "✓"),
    element("strong", "", title),
    element("p", "", copy),
  );
  return wrapper;
}

function priceChangeLabel(vehicle) {
  if (vehicle.priceDelta === null) return { value: "변동 미확인", direction: "flat", basis: "관찰 기준" };
  const direction = vehicle.priceDelta < 0 ? "down" : vehicle.priceDelta > 0 ? "up" : "flat";
  const sign = vehicle.priceDelta > 0 ? "+" : "";
  const basis = vehicle.priceChangeBasis === "previous_snapshot" ? "직전 스냅샷" : vehicle.priceChangeBasis === "first_seen" ? "첫 관찰 대비" : "관찰 대비";
  return { value: `${sign}${formatCurrency(vehicle.priceDelta)}`, direction, basis };
}

function vehicleCard(vehicle) {
  const card = element("article", "vehicle-card");
  card.dataset.tier = vehicle.decision.tier;
  if (vehicle.priorityRank !== null) card.dataset.priority = String(vehicle.priorityRank);
  if (vehicle.gone) card.dataset.gone = "true";

  const top = element("div", "card-topline");
  const badges = element("div", "card-badges");
  badges.append(element("span", "tier-badge", vehicle.gone ? "NO LONGER ACTIVE" : vehicle.decision.tier));
  if (!vehicle.gone && ["HIGH PRIORITY", "ULTRA VALUE"].includes(vehicle.monitorTier)) {
    badges.append(element("span", "minor-badge minor-badge--priority", vehicle.monitorTier));
  }
  if (vehicle.decision.verification !== "PASS" && !vehicle.gone) badges.append(element("span", "minor-badge minor-badge--verify", vehicle.decision.verification));
  if (vehicle.isNew && !vehicle.gone) badges.append(element("span", "minor-badge minor-badge--new", "NEW"));
  top.append(badges);
  if (vehicle.priorityRank !== null) top.append(element("span", "rank-badge", `#${vehicle.priorityRank}`));

  const heading = element("div", "vehicle-heading");
  heading.append(
    element("p", "vehicle-heading__meta", `${vehicle.year ?? "연식 미확인"} · ${vehicle.model || "모델 미확인"}`),
    element("h3", "", vehicle.trim || "트림 미확인"),
    element("span", "vin-full", vehicle.vin),
  );

  const priceRow = element("div", "price-row");
  priceRow.append(element("strong", "price-main", formatCurrency(vehicle.price)));
  const change = priceChangeLabel(vehicle);
  const priceChange = element("span", "price-change");
  priceChange.dataset.direction = change.direction;
  priceChange.append(element("strong", "", change.value), element("span", "", change.basis));
  priceRow.append(priceChange);

  const specs = element("div", "spec-row");
  [["Mileage", formatMiles(vehicle.miles)], ["Wheels", vehicle.wheels === null ? "미확인" : `${vehicle.wheels}”`], ["Hardware", vehicle.hardware || "미확인"]].forEach(([label, value]) => {
    const spec = element("div", "spec");
    spec.append(element("span", "", label), element("strong", "", value));
    specs.append(spec);
  });

  const colorLocation = element("p", "color-location");
  const colors = element("span");
  const colorDot = element("i", "color-dot");
  colorDot.style.backgroundColor = colorValue(vehicle.exterior);
  colors.append(colorDot, document.createTextNode(`${vehicle.exterior} exterior · ${vehicle.interior} interior`));
  const location = element("span");
  location.append(element("i", "location-dot"), document.createTextNode(vehicle.location));
  colorLocation.append(colors, location);

  const details = element("dl", "card-details");
  details.append(
    detail("First seen", formatDate(vehicle.firstSeen)),
    detail(vehicle.gone ? "Last active" : "Last seen", formatDate(vehicle.lastSeen)),
    detail("Tesla CPO", vehicle.teslaCpo === null ? "미확인" : vehicle.teslaCpo ? "Yes" : "No"),
    detail("Battery / SOH", vehicle.batteryHealth || "미확인"),
    detail("History", vehicle.autocheckScore !== null ? `AutoCheck ${vehicle.autocheckScore} · ${vehicle.titleStatus || "title 미확인"}` : vehicle.titleStatus || "AutoCheck 미확인"),
    detail("Prior use", vehicle.priorUse || "미확인"),
  );

  const otd = element("div", "otd-panel");
  const otdTop = element("div", "otd-panel__top");
  const otdRange = vehicle.otd.low === null || vehicle.otd.high === null
    ? "미확인"
    : `${formatCurrency(vehicle.otd.low)}–${formatCurrency(vehicle.otd.high)}`;
  otdTop.append(element("span", "", "Foster City estimated OTD"), element("strong", "", otdRange));
  const transportCopy = vehicle.transport === null
    ? `Transport not verified · $${vehicle.otd.transportAssumption.toLocaleString("en-US")} direct-pickup 가정${vehicle.cachedTransport !== null ? ` · cache에는 ${formatCurrency(vehicle.cachedTransport)}` : ""}`
    : `${formatCurrency(vehicle.transport)} Transport 포함 · checkout 재확인 필요`;
  otd.append(otdTop, element("p", "", transportCopy));

  const target = vehicle.decision.targetPrice !== null ? element("div", "target-line") : null;
  if (target) target.append(element("span", "", vehicle.decision.targetLabel), element("strong", "", `≤ ${formatCurrency(vehicle.decision.targetPrice)}`));

  const reasonBox = element("div", "reason-box");
  const reasonTitle = vehicle.decision.failures.length ? "고정 gate" : vehicle.decision.pending.length ? "다음 확인" : "판정 근거";
  const reasonValues = vehicle.decision.failures.length
    ? vehicle.decision.failures
    : [...vehicle.decision.reasons, ...vehicle.decision.pending.map((item) => `${item} 미확인`)];
  reasonBox.append(element("strong", "", `${reasonTitle}:`));
  const reasonList = element("ul");
  (reasonValues.length ? reasonValues : ["현재 저장 데이터의 gate를 통과했습니다."]).slice(0, 5).forEach((reason) => reasonList.append(element("li", "", reason)));
  reasonBox.append(reasonList);

  const actions = element("div", "card-actions");
  const link = element("a", "card-link");
  link.href = vehicle.teslaUrl;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.setAttribute("aria-label", `${vehicle.shortVin} Tesla 매물 새 창에서 열기`);
  link.append(element("span", "", vehicle.gone ? "Tesla 링크 확인" : "Tesla 매물 보기"), element("span", "", "↗"));
  actions.append(link);

  card.append(top, heading, priceRow, specs, colorLocation, details, otd);
  if (target) card.append(target);
  card.append(reasonBox, actions);
  return card;
}

function renderGrid(id, vehicles, emptyTitle, emptyCopy) {
  const grid = $(id);
  grid.replaceChildren();
  if (!vehicles.length) {
    grid.append(emptyState(emptyTitle, emptyCopy));
    return;
  }
  vehicles.forEach((vehicle) => grid.append(vehicleCard(vehicle)));
}

function prioritySort(a, b) {
  const monitorOrder = { "ULTRA VALUE": 0, "HIGH PRIORITY": 1, BUY: 2, FAIR: 3, WAIT: 4, EXCLUDE: 5 };
  const aRank = a.priorityRank ?? Number.MAX_SAFE_INTEGER;
  const bRank = b.priorityRank ?? Number.MAX_SAFE_INTEGER;
  return (monitorOrder[a.monitorTier] ?? 8) - (monitorOrder[b.monitorTier] ?? 8)
    || aRank - bRank
    || (TIER_ORDER[a.decision.tier] ?? 9) - (TIER_ORDER[b.decision.tier] ?? 9)
    || (a.price ?? Infinity) - (b.price ?? Infinity);
}

function renderHistory(snapshots) {
  const panel = $("history-panel");
  panel.replaceChildren();
  $("history-count").textContent = String(snapshots.length);
  if (!snapshots.length) {
    panel.append(emptyState("저장된 가격 변화가 없습니다.", "가격 이벤트가 없으면 crawl 실행 이력만 표시하며, 첫 실행 전에는 이 영역이 비어 있을 수 있습니다."));
    return;
  }
  const list = element("ol", "history-list");
  [...snapshots].sort((a, b) => new Date(b.at || 0) - new Date(a.at || 0)).forEach((snapshot) => {
    const item = element("li", "history-item");
    item.append(element("span", "history-dot"));
    const content = element("div", "history-content");
    content.append(
      element("p", "history-date", `${formatDate(snapshot.at, false)}${snapshot.model ? ` · ${snapshot.model}` : ""}`),
      element("h3", "", snapshot.title),
      element("p", "", snapshot.note),
    );
    const stats = element("div", "history-stats");
    const values = [
      ["Active", snapshot.active], ["Priority", snapshot.priority], ["BUY", snapshot.buy],
      ["New", snapshot.fresh], ["Drops", snapshot.drops], ["Gone", snapshot.gone],
      ["Events", snapshot.events], ["Alerts", snapshot.alerts],
    ];
    values.filter(([, value]) => value !== null).forEach(([label, value]) => stats.append(element("span", "history-stat", `${label} ${value}`)));
    content.append(stats);
    if (snapshot.reportUrl) {
      const link = element("a", "history-link", "해당 리포트 보기 ↗");
      link.href = reportUrl(snapshot.reportUrl);
      content.append(link);
    }
    item.append(content);
    list.append(item);
  });
  panel.append(list);
}

function setCount(id, value) {
  $(id).textContent = new Intl.NumberFormat("ko-KR").format(value);
}

function sourceStatusValue(status) {
  return String(firstDefined(status.status, status.state, status.last_status, status.last_internal_status, "unknown")).toLowerCase();
}

function sourceHealth(status, warnings) {
  const raw = sourceStatusValue(status);
  const stale = boolean(status.stale) === true;
  const hasBaseline = Boolean(firstDefined(status.last_successful_crawl, status.last_successful_at));
  if (["failed", "error"].includes(raw)) return "error";
  if (raw === "source_error") return hasBaseline ? "degraded" : "error";
  if (stale || ["degraded", "skipped", "never_run", "unknown"].includes(raw) || warnings.length) return "degraded";
  if (["healthy", "success", "ok"].includes(raw)) return "ok";
  return "degraded";
}

function renderNotice(status, warnings, source) {
  const notice = $("data-notice");
  const state = sourceHealth(status, warnings);
  const headline = String(firstDefined(status.headline, state === "error" ? "데이터 오류" : state === "degraded" ? "검증 대기 데이터" : "데이터 정상"));
  const message = String(firstDefined(status.message, status.summary, status.failure_reason, status.last_error, "최종 구매 전 Tesla checkout과 차량 이력을 다시 확인하세요."));
  const fragments = [message, ...warnings];
  if (source !== "canonical") fragments.push(`표시 소스: ${source}`);
  if (state === "ok" && !warnings.length) {
    notice.hidden = true;
    return state;
  }
  notice.hidden = false;
  notice.dataset.level = state === "error" ? "error" : "warning";
  notice.replaceChildren(element("strong", "", `${headline} — `), document.createTextNode(fragments.join(" ")));
  return warnings.length && state === "ok" ? "degraded" : state;
}

function setHealth(state, status) {
  const normalized = ["ok", "degraded", "error"].includes(state) ? state : "degraded";
  $("health-pill").dataset.state = normalized;
  $("health-label").textContent = String(firstDefined(status.health_label, status.headline, normalized === "ok" ? "SOURCE HEALTHY" : normalized === "error" ? "SOURCE FAILED" : "SOURCE DEGRADED"));
}

function attachEvent(vehicle, event, kind) {
  return {
    ...vehicle,
    isNew: kind === "new" ? true : vehicle.isNew,
    previousPrice: kind === "drop" ? event.beforePrice : vehicle.previousPrice,
    priceDelta: kind === "drop" ? event.delta : vehicle.priceDelta,
    priceChangeBasis: kind === "drop" ? "previous_snapshot" : vehicle.priceChangeBasis,
  };
}

function installInventoryControls(vehicles) {
  const search = $("inventory-search");
  const filter = $("decision-filter");
  const sort = $("inventory-sort");

  const update = () => {
    const query = search.value.trim().toLowerCase();
    const tier = filter.value;
    const visible = vehicles.filter((vehicle) => {
      const haystack = [vehicle.vin, vehicle.shortVin, vehicle.location, vehicle.exterior, vehicle.interior, vehicle.trim, vehicle.year].join(" ").toLowerCase();
      return (!query || haystack.includes(query)) && (tier === "ALL" || vehicle.decision.tier === tier);
    });
    const sorters = {
      priority: prioritySort,
      price: (a, b) => (a.price ?? Infinity) - (b.price ?? Infinity),
      mileage: (a, b) => (a.miles ?? Infinity) - (b.miles ?? Infinity),
      drop: (a, b) => (a.priceDelta ?? Infinity) - (b.priceDelta ?? Infinity),
      newest: (a, b) => new Date(b.firstSeen || 0) - new Date(a.firstSeen || 0),
    };
    visible.sort(sorters[sort.value] || prioritySort);
    renderGrid("active-grid", visible, "조건에 맞는 차량이 없습니다.", "검색어나 판정 필터를 바꿔보세요.");
    $("results-copy").textContent = `활성 ${vehicles.length}대 중 ${visible.length}대 표시`;
  };
  search.addEventListener("input", update);
  filter.addEventListener("change", update);
  sort.addEventListener("change", update);
  update();
}

function renderDashboard(data) {
  const { inventory, history, status, warnings, source } = data;
  const active = inventory.vehicles.filter((vehicle) => vehicle.available && !vehicle.gone);
  const priority = active.filter((vehicle) => vehicle.highPriority).sort(prioritySort);
  const buy = active.filter((vehicle) => vehicle.decision.tier === "BUY").sort(prioritySort);
  const confirmedBuy = buy.filter((vehicle) => vehicle.decision.verification === "PASS");
  const conditionalBuy = buy.length - confirmedBuy.length;
  const activeByVin = new Map(active.map((vehicle) => [vehicle.vin, vehicle]));
  const fresh = history.eventContract
    ? history.newEvents.map((event) => {
        const vehicle = activeByVin.get(event.vin);
        return vehicle ? attachEvent(vehicle, event, "new") : null;
      }).filter(Boolean).sort(prioritySort)
    : active.filter((vehicle) => vehicle.isNew).sort(prioritySort);
  const drops = history.eventContract
    ? history.priceDropEvents.map((event) => {
        const vehicle = activeByVin.get(event.vin);
        return vehicle ? attachEvent(vehicle, event, "drop") : null;
      }).filter(Boolean).sort((a, b) => a.priceDelta - b.priceDelta)
    : active.filter((vehicle) => vehicle.priceDelta !== null && vehicle.priceDelta <= -history.priceDropThreshold).sort((a, b) => a.priceDelta - b.priceDelta);
  const gone = history.gone.sort((a, b) => new Date(b.lastSeen || 0) - new Date(a.lastSeen || 0));

  setCount("metric-active", active.length);
  setCount("metric-priority", priority.length);
  setCount("metric-buy", buy.length);
  setCount("metric-new", fresh.length);
  setCount("metric-drops", drops.length);
  setCount("metric-gone", gone.length);
  setCount("priority-count", priority.length);
  setCount("buy-count", buy.length);
  setCount("new-count", fresh.length);
  setCount("drops-count", drops.length);
  setCount("active-count", active.length);
  setCount("gone-count", gone.length);
  $("metric-buy-hint").textContent = `${confirmedBuy.length} confirmed · ${conditionalBuy} conditional`;
  $("decision-count").textContent = String(confirmedBuy.length);
  $("otd-ceiling").textContent = formatCurrency(inventory.market.maxOtd);
  $("price-drop-threshold").textContent = formatCurrency(history.priceDropThreshold);
  const taxPercent = new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(inventory.market.taxRate * 100);
  const feeRange = `${formatCurrency(inventory.market.fixedFeeLow)}–${formatCurrency(inventory.market.fixedFeeHigh)}`;
  $("otd-method-copy").textContent = `표시 OTD는 Foster City ${taxPercent}% 세율과 고정비 ${feeRange} 추정치입니다. 최종 Transport, 세금, 등록비와 판매 상태는 Tesla checkout이 우선합니다.`;
  $("otd-formula").textContent = `OTD = (price + taxable Transport) × ${(1 + inventory.market.taxRate).toFixed(5)} + ${feeRange}`;
  $("hero-summary").textContent = `활성 ${active.length}대 중 High Priority ${priority.length}대. Foster City OTD ${formatCurrency(inventory.market.maxOtd)} cap과 고정 gate를 함께 봅니다.`;
  $("decision-copy").textContent = confirmedBuy.length
    ? `${confirmedBuy.length}대가 현재 저장 데이터의 모든 gate를 통과했습니다. checkout에서 최종 상태를 재확인하세요.`
    : priority.length
      ? `현재 확정 BUY는 없습니다. HIGH PRIORITY ${priority.length}대를 먼저 검증합니다.`
      : "현재 확정 BUY와 HIGH PRIORITY 차량은 없습니다. 다음 crawl 변화를 기다립니다.";
  const lastSuccessful = firstDefined(status.last_successful_crawl, status.last_successful_at, inventory.sourceSuccessfulAt, inventory.sourceFeedLastSeenAt);
  const lastAttempted = firstDefined(status.last_attempted_crawl, status.last_attempt_at, status.last_run_at, inventory.snapshotAt);
  const sourceStatus = sourceStatusValue(status);
  $("last-successful-crawl").textContent = formatDate(lastSuccessful);
  $("last-attempted-crawl").textContent = formatDate(lastAttempted);
  $("source-status").textContent = sourceStatus.replaceAll("_", " ").toUpperCase();
  $("source-status").dataset.state = sourceStatus;
  $("freshness").textContent = `Dashboard generated ${formatDate(inventory.snapshotAt)} · Los Angeles time · ${inventory.sourceName} · ZIP ${inventory.market.zip}`;
  const linkedReport = reportUrl(status.baseline_report_url || status.report_url);
  if (linkedReport) $("report-link").href = linkedReport;

  renderGrid("priority-grid", priority, "HIGH PRIORITY가 없습니다.", "현재 monitor_tier가 HIGH PRIORITY 또는 ULTRA VALUE인 활성 차량이 없습니다.");
  renderGrid("buy-grid", buy, "오늘 확정 BUY는 0대입니다.", "좋은 숫자만으로는 부족합니다. 가격·19인치·이력·SOH·최종 Transport를 모두 통과해야 합니다.");
  renderGrid("new-grid", fresh, "이번 crawl의 신규 차량이 없습니다.", "latest successful crawl의 new/reappeared 이벤트가 없습니다.");
  renderGrid(
    "drops-grid",
    drops,
    `${formatCurrency(history.priceDropThreshold)} 이상 PRICE DROP이 없습니다.`,
    "latest successful crawl에서 alert 기준을 넘은 활성 차량이 없습니다.",
  );
  renderGrid("gone-grid", gone, "이번 crawl에서 사라진 차량이 없습니다.", "latest successful crawl의 disappeared 이벤트가 없거나 history 데이터가 없습니다.");
  installInventoryControls(active);
  renderHistory(history.snapshots);
  setHealth(renderNotice(status, warnings, source), status);
  $("main-content").setAttribute("aria-busy", "false");
}

function renderFatal(error) {
  setHealth("error", { headline: "로드 오류" });
  const notice = $("data-notice");
  notice.hidden = false;
  notice.dataset.level = "error";
  notice.replaceChildren(element("strong", "", "재고 데이터를 표시하지 못했습니다. "), document.createTextNode(error.message));
  ["priority-grid", "buy-grid", "new-grid", "drops-grid", "active-grid", "gone-grid"].forEach((id) => {
    const grid = $(id);
    grid.replaceChildren(emptyState("데이터를 불러오지 못했습니다.", "GitHub Pages 경로와 dashboard/data JSON 배포 상태를 확인하세요.", true));
  });
  $("history-panel").replaceChildren(emptyState("History를 표시할 수 없습니다.", "활성 재고 데이터 로드가 먼저 필요합니다.", true));
  ["metric-active", "metric-priority", "metric-buy", "metric-new", "metric-drops", "metric-gone", "priority-count", "buy-count", "new-count", "drops-count", "active-count", "gone-count", "history-count"].forEach((id) => setCount(id, 0));
  $("decision-count").textContent = "0";
  $("last-successful-crawl").textContent = "미확인";
  $("last-attempted-crawl").textContent = "미확인";
  $("source-status").textContent = "FAILED";
  $("source-status").dataset.state = "failed";
  $("freshness").textContent = "스냅샷 시각을 확인할 수 없습니다.";
  $("main-content").setAttribute("aria-busy", "false");
}

loadData().then(renderDashboard).catch(renderFatal);
