const RELATIVE_UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ["year", 60 * 60 * 24 * 365],
  ["month", 60 * 60 * 24 * 30],
  ["week", 60 * 60 * 24 * 7],
  ["day", 60 * 60 * 24],
  ["hour", 60 * 60],
  ["minute", 60],
];

export function resolveLocale(language: string | undefined): string {
  return language === "my" ? "my-MM" : "en-US";
}

/**
 * The local backend stores UTC timestamps. Some SQLite rows serialize without
 * an explicit offset, so treat those as UTC instead of letting the browser
 * interpret them as local time.
 */
export function parseTimestamp(value: string): Date | null {
  const hasZone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(value);
  const date = new Date(hasZone ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDateTime(value: string | null | undefined, locale: string): string {
  if (!value) return "—";
  const date = parseTimestamp(value);
  if (!date) return "—";
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function formatRelativeDate(value: string | null | undefined, locale: string): string {
  if (!value) return "";
  const date = parseTimestamp(value);
  if (!date) return "";
  const seconds = (date.getTime() - Date.now()) / 1000;
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  for (const [unit, secondsInUnit] of RELATIVE_UNITS) {
    if (Math.abs(seconds) >= secondsInUnit) {
      return formatter.format(Math.round(seconds / secondsInUnit), unit);
    }
  }
  return formatter.format(Math.round(seconds), "second");
}

export function formatNumber(value: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(value);
}

export function pluralize(
  count: number,
  one: string,
  many: string,
): string {
  return count === 1 ? one : many;
}
