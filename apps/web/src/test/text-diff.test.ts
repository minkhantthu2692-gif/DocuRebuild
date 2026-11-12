import { describe, expect, it } from "vitest";

import { diffText } from "@/lib/text-diff";

const longPrefix = Array.from({ length: 20 }, (_, index) => `line ${index + 1}`).join("\n");

describe("diffText", () => {
  it("reports identical text without diff rows", () => {
    expect(diffText("alpha\nbeta", "alpha\nbeta")).toEqual({
      identical: true,
      tooLarge: false,
      added: 0,
      removed: 0,
      rows: [],
    });
  });

  it("treats CRLF and LF line endings as the same text", () => {
    expect(diffText("alpha\r\nbeta", "alpha\nbeta").identical).toBe(true);
  });

  it("marks removed and added lines with counts", () => {
    const result = diffText("keep\nold one\nold two", "keep\nnew one");

    expect(result.identical).toBe(false);
    expect(result.tooLarge).toBe(false);
    expect(result.added).toBe(1);
    expect(result.removed).toBe(2);
    expect(result.rows).toEqual([
      { kind: "same", text: "keep" },
      { kind: "removed", text: "old one" },
      { kind: "removed", text: "old two" },
      { kind: "added", text: "new one" },
    ]);
  });

  it("keeps a little context and collapses long unchanged runs", () => {
    const before = `${longPrefix}\nold ending`;
    const after = `${longPrefix}\nnew ending`;
    const result = diffText(before, after);

    expect(result.rows).toEqual([
      { kind: "same", text: "line 1" },
      { kind: "same", text: "line 2" },
      { kind: "gap", count: 16 },
      { kind: "same", text: "line 19" },
      { kind: "same", text: "line 20" },
      { kind: "removed", text: "old ending" },
      { kind: "added", text: "new ending" },
    ]);
  });

  it("keeps an empty line as a changed line", () => {
    const result = diffText("alpha", "alpha\n");

    expect(result.added).toBe(1);
    expect(result.rows).toEqual([
      { kind: "same", text: "alpha" },
      { kind: "added", text: "" },
    ]);
  });

  it("treats an empty document as having no lines", () => {
    expect(diffText("", "").identical).toBe(true);
    expect(diffText("", "hello")).toMatchObject({
      identical: false,
      added: 1,
      removed: 0,
      rows: [{ kind: "added", text: "hello" }],
    });
  });

  it("refuses to build an unbounded comparison for very large changes", () => {
    const before = Array.from({ length: 1_200 }, (_, index) => `before ${index}`).join("\n");
    const after = Array.from({ length: 1_200 }, (_, index) => `after ${index}`).join("\n");

    expect(diffText(before, after)).toMatchObject({
      identical: false,
      tooLarge: true,
      rows: [],
    });
  });
});
