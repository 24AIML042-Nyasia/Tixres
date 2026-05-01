export const $ = (id) => {
  if (typeof id !== "string") return null;
  return document.getElementById(id.startsWith("#") ? id.slice(1) : id);
};

export function clamp(value, min, max) {
  if (Number.isNaN(value)) return min;
  return Math.min(max, Math.max(min, value));
}

export function safeJsonParse(text) {
  if (typeof text !== "string") return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export function unwrapMetricValue(value) {
  const parsed = typeof value === "string" ? safeJsonParse(value) : value;
  if (parsed && typeof parsed === "object" && "value" in parsed) return parsed.value;
  return parsed;
}

export function fmtPercent(value, digits = 0) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${n.toFixed(digits)}%`;
}

export function fmtNumber(value, digits = 1, suffix = "") {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${n.toFixed(digits)}${suffix}`;
}

export function fmtBytes(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n)) return "—";
  const abs = Math.abs(n);
  const units = ["B", "KB", "MB", "GB", "TB"];
  let idx = 0;
  let v = abs;
  while (v >= 1024 && idx < units.length - 1) {
    v /= 1024;
    idx += 1;
  }
  const sign = n < 0 ? "-" : "";
  const digits = idx === 0 ? 0 : idx === 1 ? 0 : 1;
  return `${sign}${v.toFixed(digits)} ${units[idx]}`;
}

export function fmtRateFromMBps(mbPerSec) {
  const n = Number(mbPerSec);
  if (!Number.isFinite(n)) return "—";
  if (n >= 1) return `${n.toFixed(1)} MB/s`;
  return `${(n * 1024).toFixed(0)} KB/s`;
}

export function qsParam(name) {
  try {
    return new URL(window.location.href).searchParams.get(name);
  } catch {
    return null;
  }
}

