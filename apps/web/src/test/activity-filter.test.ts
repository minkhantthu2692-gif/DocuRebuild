import { describe, expect, it } from "vitest";

import type { HistoryEvent } from "@docurebuild/shared-types";

import {
  ACTIVITY_CATEGORIES,
  activityCategory,
  activitySearchText,
  filterActivityEvents,
} from "@/lib/activity-filter";

function event(
  id: string,
  eventType: string,
  payload: Record<string, unknown> = {},
  summary = "",
): HistoryEvent {
  return {
    id,
    event_type: eventType,
    summary,
    payload,
    created_at: "2026-11-12T09:00:00+00:00",
  };
}

const events: HistoryEvent[] = [
  event("project", "project_created"),
  event("import", "pages_imported", { count: 2 }),
  event("page", "page_processed"),
  event("region", "element_text_extracted"),
  event("ocr", "ocr_succeeded", { languages: "eng", blocks: 3 }),
  event("export", "document_exported", { format: "markdown", byte_size: 2048 }),
  event("future", "future_event", {}, "Something new happened"),
];

describe("activity filters", () => {
  it("groups known event types and keeps unknown ones in other", () => {
    expect(activityCategory("project_created")).toBe("project");
    expect(activityCategory("pages_imported")).toBe("imports");
    expect(activityCategory("page_processed")).toBe("pages");
    expect(activityCategory("element_deleted")).toBe("regions");
    expect(activityCategory("ocr_failed")).toBe("text");
    expect(activityCategory("document_exported")).toBe("export");
    expect(activityCategory("future_event")).toBe("other");
    expect(ACTIVITY_CATEGORIES).toContain("other");
  });

  it("filters by category without dropping unknown events from other", () => {
    expect(filterActivityEvents(events, "all", "").map((item) => item.id)).toEqual([
      "project",
      "import",
      "page",
      "region",
      "ocr",
      "export",
      "future",
    ]);
    expect(filterActivityEvents(events, "imports", "").map((item) => item.id)).toEqual([
      "import",
    ]);
    expect(filterActivityEvents(events, "regions", "").map((item) => item.id)).toEqual([
      "region",
    ]);
    expect(filterActivityEvents(events, "other", "").map((item) => item.id)).toEqual([
      "future",
    ]);
  });

  it("searches type, summary and metadata values case-insensitively", () => {
    expect(filterActivityEvents(events, "all", "MARKDOWN").map((item) => item.id)).toEqual([
      "export",
    ]);
    expect(filterActivityEvents(events, "all", "eng").map((item) => item.id)).toEqual([
      "ocr",
    ]);
    expect(
      filterActivityEvents(events, "all", "something new").map((item) => item.id),
    ).toEqual(["future"]);
  });

  it("never includes document text because only metadata is searched", () => {
    const log = activitySearchText(
      event("export", "document_exported", { format: "txt", byte_size: 12 }),
    );
    expect(log).toContain("document_exported");
    expect(log).toContain("txt");
    expect(log).toContain("12");
  });

  it("uses the provided text resolver for localized matches", () => {
    const filtered = filterActivityEvents(events, "all", "စာသား ထုတ်ယူမှု", (item) =>
      item.id === "ocr" ? "စာသား ထုတ်ယူမှု ပြီးစီးပြီး" : activitySearchText(item),
    );
    expect(filtered.map((item) => item.id)).toEqual(["ocr"]);
  });

  it("keeps the category filter when the search is blank", () => {
    expect(filterActivityEvents(events, "export", "   ").map((item) => item.id)).toEqual([
      "export",
    ]);
  });
});
