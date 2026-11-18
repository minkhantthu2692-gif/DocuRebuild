import { describe, expect, it } from "vitest";

import { diffInlineText, diffText, type InlineDiff } from "@/lib/text-diff";

const longPrefix = Array.from({ length: 20 }, (_, index) => `line ${index + 1}`).join("\n");

function joined(diff: InlineDiff, kinds: Array<"same" | "removed" | "added">): string {
  return diff.segments
    .filter((segment) => kinds.includes(segment.kind))
    .map((segment) => segment.text)
    .join("");
}

describe("diffInlineText", () => {
  it("returns identical text as one unchanged run", () => {
    expect(diffInlineText("same text", "same text")).toEqual({
      identical: true,
      coarse: false,
      removed: 0,
      added: 0,
      segments: [{ kind: "same", text: "same text" }],
    });
    expect(diffInlineText("", "")).toMatchObject({
      identical: true,
      removed: 0,
      added: 0,
      segments: [],
    });
  });

  it("marks a replacement inside a word", () => {
    const result = diffInlineText("tbe fox", "the fox");

    expect(result).toMatchObject({ identical: false, coarse: false, added: 1, removed: 1 });
    expect(result.segments).toEqual([
      { kind: "same", text: "t" },
      { kind: "removed", text: "b" },
      { kind: "added", text: "h" },
      { kind: "same", text: "e fox" },
    ]);
  });

  it("keeps both sides reconstructable after a multi-character insertion", () => {
    const result = diffInlineText("alpha beta", "alpha middle beta");

    expect(joined(result, ["same", "removed"])).toBe("alpha beta");
    expect(joined(result, ["same", "added"])).toBe("alpha middle beta");
    expect(result.segments.filter((segment) => segment.kind === "added")).toHaveLength(1);
  });

  it("preserves line breaks and Burmese text", () => {
    const before = "ပထမ စာကြောင်း\nဒုတိယ";
    const after = "ပထမ စာကြောင်း\nဒုတိယ စာကြောင်း";
    const result = diffInlineText(before, after);

    expect(result.identical).toBe(false);
    expect(joined(result, ["same", "removed"])).toBe(before);
    expect(joined(result, ["same", "added"])).toBe(after);
    expect(joined(result, ["same", "added"])).toContain("\n");
  });

  it("falls back to one coarse change for a very large rewrite", () => {
    const result = diffInlineText("a".repeat(500), "b".repeat(500));

    expect(result.identical).toBe(false);
    expect(result.coarse).toBe(true);
    expect(result.segments.map((segment) => segment.kind)).toEqual([
      "removed",
      "added",
    ]);
  });

  it("treats an empty original as a single addition", () => {
    const result = diffInlineText("", "hello");

    expect(result).toMatchObject({ identical: false, coarse: false, added: 5, removed: 0 });
    expect(result.segments).toEqual([{ kind: "added", text: "hello" }]);
  });
});

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
