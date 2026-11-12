import { getSchema } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { describe, expect, it } from "vitest";

import { findMatches } from "@/lib/editor-search";

const schema = getSchema([StarterKit]);

function docFrom(content: unknown[]) {
  return schema.nodeFromJSON({ type: "doc", content });
}

describe("findMatches", () => {
  it("returns every occurrence and real document positions", () => {
    const doc = docFrom([
      {
        type: "paragraph",
        content: [{ type: "text", text: "alpha beta alpha" }],
      },
    ]);

    const matches = findMatches(doc, "alpha");

    expect(matches).toHaveLength(2);
    for (const match of matches) {
      expect(doc.textBetween(match.from, match.to)).toBe("alpha");
    }
  });

  it("matches across adjacent marks but not across paragraphs", () => {
    const doc = docFrom([
      {
        type: "paragraph",
        content: [
          { type: "text", text: "Alpha ", marks: [{ type: "bold" }] },
          { type: "text", text: "beta", marks: [{ type: "italic" }] },
        ],
      },
      {
        type: "paragraph",
        content: [{ type: "text", text: "gamma" }],
      },
    ]);

    const spanning = findMatches(doc, "Alpha beta");
    expect(spanning).toHaveLength(1);
    expect(doc.textBetween(spanning[0].from, spanning[0].to)).toBe("Alpha beta");

    expect(findMatches(doc, "betagamma")).toHaveLength(0);
    expect(findMatches(doc, "beta gamma")).toHaveLength(0);
  });

  it("respects the match-case option", () => {
    const doc = docFrom([
      {
        type: "paragraph",
        content: [
          { type: "text", text: "Alpha " },
          { type: "text", text: "alpha" },
        ],
      },
    ]);

    expect(findMatches(doc, "alpha")).toHaveLength(2);
    expect(findMatches(doc, "alpha", true)).toHaveLength(1);
    expect(findMatches(doc, "Alpha", true)).toHaveLength(1);
  });

  it("does not overlap matches", () => {
    const doc = docFrom([
      {
        type: "paragraph",
        content: [{ type: "text", text: "aaaa" }],
      },
    ]);

    expect(findMatches(doc, "aa")).toHaveLength(2);
  });

  it("returns nothing for an empty query", () => {
    const doc = docFrom([
      { type: "paragraph", content: [{ type: "text", text: "text" }] },
    ]);

    expect(findMatches(doc, "")).toEqual([]);
  });

  it("does not match across a hard break", () => {
    const doc = docFrom([
      {
        type: "paragraph",
        content: [
          { type: "text", text: "alpha" },
          { type: "hardBreak" },
          { type: "text", text: "beta" },
        ],
      },
    ]);

    expect(findMatches(doc, "alphabeta")).toHaveLength(0);
    expect(findMatches(doc, "beta")).toHaveLength(1);
  });
});
