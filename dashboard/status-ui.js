const text = (value) => (value === null || value === undefined ? "" : String(value).trim());

const trueish = (value) => {
  if (typeof value === "boolean") return value;
  const normalized = text(value).toLowerCase();
  if (["true", "yes", "1"].includes(normalized)) return true;
  if (["false", "no", "0", ""].includes(normalized)) return false;
  return Boolean(value);
};

const looksTechnical = (value) => {
  const message = text(value);
  return /request failed after|HTTP(?:\s+Error)?\s+\d{3}|Forbidden|Traceback|SourceError/i.test(message);
};

const statusValue = (status = {}) => text(
  status.status ?? status.state ?? status.last_status ?? status.last_internal_status ?? "unknown",
).toLowerCase();

const hasBaseline = (status = {}) => Boolean(
  status.last_verified_snapshot ?? status.last_successful_crawl ?? status.last_successful_at,
);

const failureCode = (status = {}, candidate = "") => {
  const typedErrorCode = text(status.failure_kind ?? status.error_code).toLowerCase();
  const explicit = Number(status.failure_http_status ?? status.http_status);
  if (Number.isFinite(explicit) && explicit >= 100) return explicit;
  const typedMatch = typedErrorCode.match(/^http_(\d{3})$/);
  if (typedMatch) return Number(typedMatch[1]);
  if (typedErrorCode) return null;
  const match = text(candidate || status.failure_reason).match(/HTTP(?:\s+Error)?\s+(\d{3})/i);
  return match ? Number(match[1]) : null;
};

export function sourceHealth(status = {}, warnings = []) {
  const raw = statusValue(status);
  const stale = trueish(status.stale);
  if (["failed", "error"].includes(raw)) return "error";
  if (raw === "source_error") return hasBaseline(status) ? "degraded" : "error";
  if (stale || ["degraded", "skipped", "never_run", "unknown"].includes(raw) || warnings.length) {
    return "degraded";
  }
  if (["healthy", "success", "ok"].includes(raw)) return "ok";
  return "degraded";
}

function fallbackMessage(status, state, suppliedMessage = "") {
  const baseline = hasBaseline(status);
  const code = failureCode(status, suppliedMessage);
  if (state === "ok") return "Tesla 재고 소스를 정상적으로 확인했습니다.";
  if (!baseline) return "Tesla 재고 소스를 확인하지 못했고 표시할 마지막 스냅샷도 없습니다.";
  if (code === 403 || ["access_denied", "http_403"].includes(status.failure_kind)) {
    return "Tesla 재고 소스가 자동 요청을 거부해 최신 가격과 판매 여부를 확인하지 못했습니다. 마지막으로 확인된 스냅샷을 보존해 표시합니다.";
  }
  if (code === 429 || ["rate_limited", "http_429"].includes(status.failure_kind)) {
    return "Tesla 재고 소스의 요청 제한으로 최신 가격과 판매 여부를 확인하지 못했습니다. 마지막으로 확인된 스냅샷을 보존해 표시합니다.";
  }
  return "Tesla 재고 소스를 갱신하지 못했습니다. 마지막으로 확인된 스냅샷을 보존해 표시합니다.";
}

export function statusPresentation(status = {}, warnings = [], source = "canonical") {
  const state = sourceHealth(status, warnings);
  const baseline = hasBaseline(status);
  const declaredMode = text(status.data_mode).toLowerCase();
  const dataMode = ["live", "last_known", "unavailable"].includes(declaredMode)
    ? declaredMode
    : state === "ok" ? "live" : baseline ? "last_known" : "unavailable";
  const defaultHeadline = state === "ok"
    ? "재고 데이터 정상"
    : dataMode === "last_known" ? "재고 갱신 지연" : "재고를 불러오지 못했습니다";
  const suppliedHeadline = text(status.headline);
  const suppliedMessage = text(status.message ?? status.summary);
  const headline = suppliedHeadline && !looksTechnical(suppliedHeadline) ? suppliedHeadline : defaultHeadline;
  const message = suppliedMessage && !looksTechnical(suppliedMessage)
    ? suppliedMessage
    : fallbackMessage(status, state, suppliedMessage);
  const fragments = [message, ...warnings.map(text).filter(Boolean)];
  if (source !== "canonical") fragments.push(`표시 소스: ${source}`);
  const defaultHealthLabel = state === "ok"
    ? "SOURCE HEALTHY"
    : state === "error" ? "SOURCE FAILED" : "SOURCE DEGRADED";
  return {
    state,
    dataMode,
    headline,
    message: fragments.join(" "),
    healthLabel: text(status.health_label) || defaultHealthLabel,
  };
}

export function historyRunPresentation(entry = {}) {
  const status = statusValue(entry);
  const suppliedTitle = text(entry.details?.title);
  const suppliedNote = text(entry.details?.note ?? entry.error ?? entry.reason);
  const sourceFailed = status === "source_error" || looksTechnical(suppliedNote);
  if (sourceFailed) {
    const code = failureCode(entry, suppliedNote);
    const note = code === 403
      ? "Tesla 재고 소스가 자동 요청을 거부해 마지막으로 확인된 스냅샷을 보존했습니다."
      : code === 429
        ? "Tesla 재고 소스의 요청 제한으로 마지막으로 확인된 스냅샷을 보존했습니다."
        : "Tesla 재고 소스를 갱신하지 못해 마지막으로 확인된 스냅샷을 보존했습니다.";
    return { title: "재고 갱신 실패", note };
  }
  return {
    title: suppliedTitle || `Crawler ${status.replaceAll("_", " ")}`,
    note: suppliedNote || (status === "success" ? "Tesla 재고 소스를 확인했습니다." : "Crawler 실행 기록입니다."),
  };
}
