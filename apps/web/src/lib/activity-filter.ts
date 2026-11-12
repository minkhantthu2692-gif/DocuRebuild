import type { HistoryEvent } from "@docurebuild/shared-types";

/** Filter groups shown in the project activity dialog. */
export const ACTIVITY_CATEGORIES = [
  "all",
  "project",
  "imports",
  "pages",
  "regions",
  "text",
  "export",
  "other",
] as const;

export type ActivityCategory = (typeof ACTIVITY_CATEGORIES)[number];

type KnownCategory = Exclude<ActivityCategory, "all" | "other">;

/**
 * Event type to filter group. Unknown event types (for example from a newer
 * build) fall into `other` instead of disappearing when a filter is active.
 */
const CATEGORY_BY_EVENT: Record<string, KnownCategory> = {
  project_created: "project",
  project_backup_created: "project",
  project_restored: "project",
  pages_imported: "imports",
  pages_import_cancelled: "imports",
  page_processed: "pages",
  page_edits_reset: "pages",
  page_deleted: "pages",
  element_extracted: "regions",
  element_updated: "regions",
  element_text_extracted: "regions",
  element_text_updated: "regions",
  element_deleted: "regions",
  document_exported: "export",
  ocr_started: "text",
  ocr_succeeded: "text",
  ocr_failed: "text",
};

export function activityCategory(eventType: string): ActivityCategory {
  return CATEGORY_BY_EVENT[eventType] ?? "other";
}

/** Metadata, type and stored summary; never document text or OCR output. */
export function activitySearchText(event: HistoryEvent): string {
  const payloadValues = Object.values(event.payload ?? {})
    .filter((value) => typeof value === "string" || typeof value === "number")
    .map((value) => String(value));
  return [event.event_type, event.summary, ...payloadValues].join(" ").toLocaleLowerCase();
}

/**
 * Filter newest-first events by category and free text. `textFor` lets the UI
 * include localized labels and detail values in the search without putting
 * translation into this module.
 */
export function filterActivityEvents(
  events: HistoryEvent[],
  category: ActivityCategory,
  search: string,
  textFor: (event: HistoryEvent) => string = activitySearchText,
): HistoryEvent[] {
  const needle = search.trim().toLocaleLowerCase();
  return events.filter((event) => {
    if (category !== "all" && activityCategory(event.event_type) !== category) {
      return false;
    }
    if (!needle) return true;
    return textFor(event).toLocaleLowerCase().includes(needle);
  });
}
