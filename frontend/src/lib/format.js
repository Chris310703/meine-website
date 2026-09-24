const nf = (digits = 0) =>
  new Intl.NumberFormat("de-DE", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export function num(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  return nf(digits).format(value);
}

export function euro(value, digits = 2) {
  if (value === null || value === undefined) return "–";
  return new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR", minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
}

export function money(value, currency = "EUR", digits = 2) {
  if (value === null || value === undefined) return "–";
  try {
    return new Intl.NumberFormat("de-DE", { style: "currency", currency, minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
  } catch {
    return `${num(value, digits)} ${currency}`;
  }
}

export function pct(value, digits = 1, sign = false) {
  if (value === null || value === undefined) return "–";
  const s = sign && value > 0 ? "+" : "";
  return `${s}${num(value, digits)} %`;
}

/** Stunden (Dezimal) → "7:32 h" */
export function hours(h) {
  if (h === null || h === undefined) return "–";
  const total = Math.round(h * 60);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")} h`;
}

/** Sekunden → "1:05 h" bzw. "45 min" */
export function duration(seconds) {
  if (!seconds && seconds !== 0) return "–";
  const m = Math.round(seconds / 60);
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")} h`;
}

export function minutesText(m) {
  if (m === null || m === undefined) return "–";
  if (m < 60) return `${Math.round(m)} min`;
  const h = Math.floor(m / 60);
  const r = Math.round(m % 60);
  return r ? `${h} h ${r} min` : `${h} h`;
}

/** Pace in min/km aus Geschwindigkeit m/s */
export function paceFromSpeed(speed) {
  if (!speed) return "–";
  return paceText(1000 / speed / 60);
}

export function paceText(minPerKm) {
  if (!minPerKm || !Number.isFinite(minPerKm)) return "–";
  let m = Math.floor(minPerKm);
  let s = Math.round((minPerKm - m) * 60);
  if (s === 60) {
    m += 1;
    s = 0;
  }
  return `${m}:${String(s).padStart(2, "0")} /km`;
}

export function km(meters, digits = 1) {
  if (!meters) return "–";
  return `${num(meters / 1000, digits)} km`;
}

const WEEKDAYS = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
const WEEKDAYS_LONG = ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"];
const MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"];

export function toDate(value) {
  if (!value) return null;
  if (value instanceof Date) return value;
  // "YYYY-MM-DD" als lokales Datum interpretieren
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [y, m, d] = value.split("-").map(Number);
    return new Date(y, m - 1, d);
  }
  return new Date(value);
}

export function isoDate(d) {
  const date = toDate(d);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function todayIso() {
  return isoDate(new Date());
}

export function dateShort(value) {
  const d = toDate(value);
  if (!d) return "–";
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.`;
}

export function dateLong(value) {
  const d = toDate(value);
  if (!d) return "–";
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`;
}

export function weekdayShort(value) {
  const d = toDate(value);
  return d ? WEEKDAYS[d.getDay()] : "";
}

export function weekdayLong(value) {
  const d = toDate(value);
  return d ? WEEKDAYS_LONG[d.getDay()] : "";
}

export function dayLabel(value) {
  const d = toDate(value);
  if (!d) return "–";
  return `${WEEKDAYS[d.getDay()]}, ${dateShort(d)}`;
}

export function monthName(index) {
  return MONTHS[index];
}

export function timeText(value) {
  const d = toDate(value);
  if (!d) return "–";
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function relativeDay(value) {
  const d = toDate(value);
  if (!d) return "";
  const today = toDate(todayIso());
  const target = toDate(isoDate(d));
  const diff = Math.round((target - today) / 86400000);
  if (diff === 0) return "Heute";
  if (diff === 1) return "Morgen";
  if (diff === -1) return "Gestern";
  if (diff > 1 && diff < 7) return WEEKDAYS_LONG[target.getDay()];
  return dateShort(target);
}

export function dateTimeText(value) {
  const d = toDate(value);
  if (!d) return "–";
  return `${relativeDay(d)}, ${timeText(d)}`;
}

export function addDays(value, n) {
  const d = new Date(toDate(value));
  d.setDate(d.getDate() + n);
  return d;
}

export function startOfWeek(value) {
  const d = new Date(toDate(value));
  const day = (d.getDay() + 6) % 7;
  d.setDate(d.getDate() - day);
  d.setHours(0, 0, 0, 0);
  return d;
}

export function signed(value, digits = 0, unit = "") {
  if (value === null || value === undefined) return "–";
  const s = value > 0 ? "+" : value < 0 ? "−" : "±";
  return `${s}${num(Math.abs(value), digits)}${unit}`;
}
