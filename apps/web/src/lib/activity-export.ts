/**
 * Local activity-log export.
 *
 * The export is built in the browser from the events already loaded in the
 * dialog, so it never sends log data anywhere and it can honour the active
 * category and search. CSV is meant for spreadsheet review; JSON keeps the raw
 * payload for archival.
 */

import type { HistoryEvent } from "@docurebuild/shared-types";

/** Stable, machine-readable header; values may be localized. */
export const ACTIVITY_EXPORT_HEADER = [
  "timestamp",
  "event_type",
  "label",
  "details",
  "summary",
  "payload",
] as const;

export const ACTIVITY_EXPORT_FORMAT = "docurebuild.activity";
export const ACTIVITY_EXPORT_VERSION = 1;

export interface ActivityExportItem {
  event: HistoryEvent;
  /** Localized event label, as shown in the dialog. */
  label: string;
  /** Localized detail lines, as shown in the dialog. */
  details: string[];
}

export interface ActivityExportFilters {
  category: string;
  search: string;
}

// Control characters cannot appear in a download name; strip them with the
// path and shell metacharacters. `no-control-regex` is intentional here.
// eslint-disable-next-line no-control-regex
const UNSAFE_FILENAME = /[\u0000-\u001f\u007f/\\:*?"<>|]+/g;
/** Spreadsheet applications may evaluate these leading characters. */
const FORMULA_START = /^[=+\-@\t\r]/;
const MUST_QUOTE = /[",\r\n]/;

function csvField(value: string): string {
  // Neutralise spreadsheet formulas before quoting. The value stays readable,
  // and a log created from a file name such as `=cmd` cannot execute.
  const safe = FORMULA_START.test(value) ? `'${value}` : value;
  return MUST_QUOTE.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

/** RFC 4180 CSV with a trailing CRLF; no byte-order mark. */
export function buildActivityCsv(items: ActivityExportItem[]): string {
  const rows: string[][] = items.map(({ event, label, details }) => [
    event.created_at,
    event.event_type,
    label,
    details.join(" · "),
    event.summary,
    JSON.stringify(event.payload ?? {}),
  ]);
  const lines = [ACTIVITY_EXPORT_HEADER as readonly string[], ...rows].map((row) =>
    row.map(csvField).join(","),
  );
  return `${lines.join("\r\n")}\r\n`;
}

/**
 * JSON archive of the exported events. The filter state is recorded so the
 * file explains why it contains fewer events than the project has.
 */
export function buildActivityJson(
  items: ActivityExportItem[],
  options: {
    projectId: string;
    filters: ActivityExportFilters;
    now?: Date;
  },
): string {
  const body = {
    format: ACTIVITY_EXPORT_FORMAT,
    version: ACTIVITY_EXPORT_VERSION,
    exported_at: (options.now ?? new Date()).toISOString(),
    project_id: options.projectId,
    filters: options.filters,
    count: items.length,
    events: items.map(({ event, label, details }) => ({
      ...event,
      label,
      details,
    })),
  };
  return `${JSON.stringify(body, null, 2)}\n`;
}

/** Portable download name, e.g. `My book-activity-20261112.csv`. */
export function activityExportFilename(
  projectName: string,
  extension: "csv" | "json",
  date: Date = new Date(),
): string {
  const cleaned =
    projectName
      .replace(UNSAFE_FILENAME, "-")
      .trim()
      .replace(/^[ .\-_]+|[ .\-_]+$/g, "")
      .slice(0, 80)
      .replace(/[ .\-_]+$/g, "") || "project";
  const stamp = [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("");
  return `${cleaned}-activity-${stamp}.${extension}`;
}
