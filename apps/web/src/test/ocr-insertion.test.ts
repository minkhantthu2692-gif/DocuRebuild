import { describe, expect, it } from "vitest";

import { ocrInsertionContent } from "@/lib/ocr-insertion";

describe("OCR insertion content", () => {
  it("splits paragraphs on blank lines", () => {
    const nodes = ocrInsertionContent("First paragraph.\n\nSecond paragraph.", null);

    expect(nodes).toHaveLength(2);
    expect(nodes[0]).toEqual({
      type: "paragraph",
      content: [{ type: "text", text: "First paragraph." }],
    });
    expect(nodes[1]).toEqual({
      type: "paragraph",
      content: [{ type: "text", text: "Second paragraph." }],
    });
  });

  it("keeps single line breaks as hard breaks", () => {
    const nodes = ocrInsertionContent("Line one\nLine two", null);

    expect(nodes).toHaveLength(1);
    expect(nodes[0].content).toEqual([
      { type: "text", text: "Line one" },
      { type: "hardBreak" },
      { type: "text", text: "Line two" },
    ]);
  });

  it("handles Windows line endings", () => {
    const nodes = ocrInsertionContent("First line\r\nSecond\r\n\r\nNext paragraph", null);

    expect(nodes).toHaveLength(2);
    expect(nodes[0].content).toEqual([
      { type: "text", text: "First line" },
      { type: "hardBreak" },
      { type: "text", text: "Second" },
    ]);
    expect(nodes[1]).toEqual({
      type: "paragraph",
      content: [{ type: "text", text: "Next paragraph" }],
    });
  });

  it("appends the source note as a blockquote", () => {
    const nodes = ocrInsertionContent("Body", "Source: page 2");

    expect(nodes).toHaveLength(2);
    expect(nodes[1]).toEqual({
      type: "blockquote",
      content: [
        {
          type: "paragraph",
          content: [{ type: "text", text: "Source: page 2" }],
        },
      ],
    });
  });

  it("omits the note when none is requested", () => {
    expect(ocrInsertionContent("Body", null)).toHaveLength(1);
  });
});
