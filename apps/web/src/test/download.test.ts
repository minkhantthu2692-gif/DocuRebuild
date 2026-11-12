import { describe, expect, it } from "vitest";

import { filenameFromDisposition } from "@/lib/download";

describe("backup download names", () => {
  it("prefers the UTF-8 filename so Burmese names survive", () => {
    const filename = "စာမျက်နှာ-20261112.zip";
    const header =
      'attachment; filename="project-20261112.zip"; ' +
      `filename*=UTF-8''${encodeURIComponent(filename)}`;
    expect(filenameFromDisposition(header)).toBe(filename);
  });

  it("falls back to the quoted ASCII filename", () => {
    expect(
      filenameFromDisposition('attachment; filename="project-backup.zip"'),
    ).toBe("project-backup.zip");
    expect(
      filenameFromDisposition("attachment; filename=project-backup.zip"),
    ).toBe("project-backup.zip");
  });

  it("returns null for missing or malformed headers", () => {
    expect(filenameFromDisposition(null)).toBeNull();
    expect(filenameFromDisposition("attachment")).toBeNull();
    expect(
      filenameFromDisposition("attachment; filename*=UTF-8''%E0%A4%A"),
    ).toBeNull();
  });
});
