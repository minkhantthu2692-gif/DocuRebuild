import { describe, expect, it } from "vitest";

import {
  formatDateTime,
  formatFileSize,
  formatNumber,
  formatRelativeDate,
  parseTimestamp,
  pluralize,
  resolveLocale,
} from "@/lib/format";

describe("formatting", () => {
  it("maps application languages to BCP 47 locales", () => {
    expect(resolveLocale("my")).toBe("my-MM");
    expect(resolveLocale("en")).toBe("en-US");
    expect(resolveLocale(undefined)).toBe("en-US");
  });

  it("formats dates and rejects missing values", () => {
    expect(formatDateTime(null, "en-US")).toBe("—");
    expect(formatDateTime("not-a-date", "en-US")).toBe("—");
    expect(formatDateTime("2024-01-02T03:04:00Z", "en-US")).toContain("2024");
  });

  it("formats relative dates and numbers", () => {
    expect(formatRelativeDate(null, "en-US")).toBe("");
    expect(formatNumber(1200, "en-US")).toBe("1,200");
  });

  it("formats file sizes with locale-aware digits", () => {
    expect(formatFileSize(0, "en-US")).toBe("0 B");
    expect(formatFileSize(512, "en-US")).toBe("512 B");
    expect(formatFileSize(1536, "en-US")).toBe("1.5 KB");
    expect(formatFileSize(12 * 1024 * 1024, "en-US")).toBe("12 MB");
    expect(formatFileSize(Number.NaN, "en-US")).toBe("0 B");
  });

  it("treats zone-less backend timestamps as UTC", () => {
    expect(parseTimestamp("2026-11-08T09:45:59.809874")?.toISOString()).toBe(
      "2026-11-08T09:45:59.809Z",
    );
    expect(parseTimestamp("2026-11-08T09:45:59+07:00")?.toISOString()).toBe(
      "2026-11-08T02:45:59.000Z",
    );
    expect(parseTimestamp("not-a-date")).toBeNull();
  });

  it("selects singular and plural strings", () => {
    expect(pluralize(1, "page", "pages")).toBe("page");
    expect(pluralize(2, "page", "pages")).toBe("pages");
  });
});
