import { describe, expect, it } from "vitest";

import type { HistoryEvent } from "@docurebuild/shared-types";

import {
  activityExportFilename,
  buildActivityCsv,
  buildActivityJson,
  type ActivityExportItem,
} from "@/lib/activity-export";

function event(patch: Partial<HistoryEvent> = {}): HistoryEvent {
  return {
    id: "event-1",
    event_type: "document_exported",
    summary: "Document exported.",
    payload: { format: "markdown", byte_size: 2048 },
    created_at: "2026-11-12T10:00:00+00:00",
    ...patch,
  };
}

function item(patch: Partial<HistoryEvent> = {}): ActivityExportItem {
  const record = event(patch);
  return {
    event: record,
    label: "Document exported",
    details: ["Format: Markdown (.md)", "Size: 2 KB"],
  };
}

describe("activity export", () => {
  it("writes a stable header and one row per visible event", () => {
    const csv = buildActivityCsv([
      item(),
      item({
        id: "event-2",
        event_type: "future_event",
        summary: "Something new happened",
        payload: {},
        created_at: "2026-11-12T09:00:00+00:00",
      }),
    ]);
    const lines = csv.split("\r\n");

    expect(lines[0]).toBe("timestamp,event_type,label,details,summary,payload");
    expect(lines[1]).toBe(
      '2026-11-12T10:00:00+00:00,document_exported,Document exported,Format: Markdown (.md) · Size: 2 KB,Document exported.,"{""format"":""markdown"",""byte_size"":2048}"',
    );
    expect(lines[2]).toContain("Something new happened");
    expect(csv.endsWith("\r\n")).toBe(true);
  });

  it("quotes commas, quotes and line breaks and always ends with CRLF", () => {
    const csv = buildActivityCsv([
      item({ summary: 'Line one, "quoted"\nline two' }),
    ]);

    expect(csv).toContain('"Line one, ""quoted""\nline two"');
  });

  it("neutralises spreadsheet formulas in exported values", () => {
    const csv = buildActivityCsv([
      item({ summary: "=HYPERLINK(\"https://example.test\")" }),
      item({ id: "event-2", summary: "+1-555" }),
    ]);
    const lines = csv.split("\r\n");

    expect(lines[1]).toContain("'=HYPERLINK");
    expect(lines[2]).toContain("'+1-555");
    // The original value is preserved after the protective apostrophe.
    expect(lines[2]).not.toContain("'+'+1-555");
  });

  it("exports only the header when no event matches", () => {
    expect(buildActivityCsv([])).toBe(
      "timestamp,event_type,label,details,summary,payload\r\n",
    );
  });

  it("keeps raw metadata and records the active filters in JSON", () => {
    const json = buildActivityJson([item()], {
      projectId: "project-1",
      filters: { category: "export", search: "markdown" },
      now: new Date("2026-11-12T10:15:00.000Z"),
    });
    const body = JSON.parse(json);

    expect(body).toMatchObject({
      format: "docurebuild.activity",
      version: 1,
      exported_at: "2026-11-12T10:15:00.000Z",
      project_id: "project-1",
      filters: { category: "export", search: "markdown" },
      count: 1,
    });
    expect(body.events[0]).toMatchObject({
      id: "event-1",
      event_type: "document_exported",
      summary: "Document exported.",
      payload: { format: "markdown", byte_size: 2048 },
      label: "Document exported",
      details: ["Format: Markdown (.md)", "Size: 2 KB"],
    });
    expect(json.endsWith("\n")).toBe(true);
  });

  it("builds a portable dated filename", () => {
    expect(
      activityExportFilename("My book: draft/1", "csv", new Date(2026, 10, 2)),
    ).toBe("My book- draft-1-activity-20261102.csv");
    expect(activityExportFilename("  ", "json", new Date(2026, 0, 1))).toBe(
      "project-activity-20260101.json",
    );
    expect(activityExportFilename("မြန်မာစာ", "csv", new Date(2026, 11, 31))).toBe(
      "မြန်မာစာ-activity-20261231.csv",
    );
  });
});
