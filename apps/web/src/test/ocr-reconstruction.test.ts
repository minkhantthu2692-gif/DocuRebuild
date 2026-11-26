import { describe, expect, it } from "vitest";

import {
  ocrReconstructionContent,
  type OcrReconstructionBlock,
} from "@/lib/ocr-reconstruction";

function block(overrides: Partial<OcrReconstructionBlock>): OcrReconstructionBlock {
  return {
    kind: "paragraph",
    text: "",
    x: 100,
    y: 100,
    width: 600,
    height: 32,
    ...overrides,
  };
}

function paragraphTexts(nodes: ReturnType<typeof ocrReconstructionContent>): string[] {
  return nodes
    .filter((node) => node.type === "paragraph")
    .map((node) =>
      (node.content ?? [])
        .filter((child) => child.type === "text")
        .map((child) => child.text ?? "")
        .join(""),
    );
}

describe("OCR paragraph reconstruction", () => {
  it("joins wrapped lines inside one block into a flowing paragraph", () => {
    const nodes = ocrReconstructionContent(
      [
        block({
          text: "This is the first line of a paragraph\nthat continues on the next line.",
          height: 64,
        }),
      ],
      null,
    );

    expect(nodes).toEqual([
      {
        type: "paragraph",
        content: [
          {
            type: "text",
            text: "This is the first line of a paragraph that continues on the next line.",
          },
        ],
      },
    ]);
    expect(JSON.stringify(nodes)).not.toContain("hardBreak");
  });

  it("keeps paragraphs separated by a real vertical gap", () => {
    const nodes = ocrReconstructionContent(
      [
        block({ text: "First paragraph.", y: 100 }),
        block({ text: "Second paragraph.", y: 200 }),
      ],
      null,
    );

    expect(paragraphTexts(nodes)).toEqual(["First paragraph.", "Second paragraph."]);
  });

  it("merges sparse single-line blocks even when a line ends with a full stop", () => {
    const nodes = ocrReconstructionContent(
      [
        block({ text: "The first visual line ends here.", y: 100 }),
        block({ text: "The second visual line starts here.", y: 132 }),
        block({ text: "The third visual line closes it.", y: 164 }),
      ],
      null,
    );

    expect(paragraphTexts(nodes)).toEqual([
      "The first visual line ends here. The second visual line starts here. The third visual line closes it.",
    ]);
  });

  it("does not merge side-by-side columns and reads left before right", () => {
    const nodes = ocrReconstructionContent(
      [
        block({ text: "Left column line one", x: 100, y: 100, width: 240 }),
        block({ text: "Right column line one", x: 400, y: 100, width: 240 }),
        block({ text: "Left column line two", x: 100, y: 132, width: 240 }),
        block({ text: "Right column line two", x: 400, y: 132, width: 240 }),
      ],
      null,
    );

    expect(paragraphTexts(nodes)).toEqual([
      "Left column line one Left column line two",
      "Right column line one Right column line two",
    ]);
  });

  it("keeps a heading as a heading and infers a level from its size", () => {
    const nodes = ocrReconstructionContent(
      [
        block({ kind: "heading", text: "Chapter One", x: 100, y: 100, width: 300, height: 60 }),
        block({ text: "First body paragraph.", x: 100, y: 190, width: 600, height: 24 }),
        block({ text: "Second body paragraph.", x: 100, y: 240, width: 600, height: 24 }),
      ],
      null,
    );

    expect(nodes[0]).toEqual({
      type: "heading",
      attrs: { level: 1 },
      content: [{ type: "text", text: "Chapter One" }],
    });
    expect(paragraphTexts(nodes)).toEqual([
      "First body paragraph.",
      "Second body paragraph.",
    ]);
  });

  it("does not merge a heading into the body paragraph below it", () => {
    const nodes = ocrReconstructionContent(
      [
        block({ kind: "heading", text: "Chapter One", x: 100, y: 100, width: 300, height: 48 }),
        block({ text: "Body starts here.", x: 100, y: 140, width: 600, height: 24 }),
      ],
      null,
    );

    expect(nodes[0].type).toBe("heading");
    expect(paragraphTexts(nodes)).toEqual(["Body starts here."]);
  });

  it("demotes a long full-width line misclassified as a heading", () => {
    const text =
      "A final full-width paragraph closes the page. It should join the lines above";
    const nodes = ocrReconstructionContent(
      [
        block({ kind: "heading", text, x: 100, y: 100, width: 600, height: 32 }),
        block({
          text: "into a single editable paragraph with normal wrapping.",
          x: 100,
          y: 150,
          width: 600,
          height: 32,
        }),
      ],
      null,
    );

    expect(nodes).toEqual([
      {
        type: "paragraph",
        content: [
          {
            type: "text",
            text: "A final full-width paragraph closes the page. It should join the lines above into a single editable paragraph with normal wrapping.",
          },
        ],
      },
    ]);
  });

  it("builds an ordered list from one multi-line list block", () => {
    const nodes = ocrReconstructionContent(
      [
        block({
          kind: "list_item",
          text: "1. First item\n2. Second item\n3. Third item",
          x: 100,
          y: 100,
          width: 300,
          height: 90,
        }),
      ],
      null,
    );

    expect(nodes).toEqual([
      {
        type: "orderedList",
        content: [
          { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "First item" }] }] },
          { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "Second item" }] }] },
          { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "Third item" }] }] },
        ],
      },
    ]);
  });

  it("keeps a list's original starting number", () => {
    const nodes = ocrReconstructionContent(
      [
        block({
          kind: "list_item",
          text: "3. Third item\n4. Fourth item",
          x: 100,
          y: 100,
          width: 300,
          height: 64,
        }),
      ],
      null,
    );

    expect(nodes[0]).toMatchObject({
      type: "orderedList",
      attrs: { start: 3 },
    });
    expect(nodes[0].content).toHaveLength(2);
  });

  it("merges consecutive sparse ordered-list blocks into one list", () => {
    const nodes = ocrReconstructionContent(
      [
        block({ kind: "list_item", text: "1. First item", x: 100, y: 100, width: 300 }),
        block({ kind: "list_item", text: "2. Second item", x: 100, y: 132, width: 300 }),
      ],
      null,
    );

    expect(nodes).toHaveLength(1);
    expect(nodes[0].type).toBe("orderedList");
    expect(nodes[0].content).toHaveLength(2);
  });

  it("builds a bulleted list and attaches wrapped item lines", () => {
    const nodes = ocrReconstructionContent(
      [
        block({
          kind: "list_item",
          text: "- A long item that wraps\nonto a second line\n- Second item",
          x: 100,
          y: 100,
          width: 300,
          height: 90,
        }),
      ],
      null,
    );

    expect(nodes[0].type).toBe("bulletList");
    expect(nodes[0].content?.[0]).toEqual({
      type: "listItem",
      content: [
        {
          type: "paragraph",
          content: [{ type: "text", text: "A long item that wraps onto a second line" }],
        },
      ],
    });
  });

  it("preserves table-like block line layout", () => {
    const nodes = ocrReconstructionContent(
      [
        block({
          kind: "table",
          text: "Name  Value\nAlpha  1",
          x: 100,
          y: 100,
          width: 300,
          height: 60,
        }),
      ],
      null,
    );

    expect(nodes).toEqual([
      {
        type: "paragraph",
        content: [
          { type: "text", text: "Name  Value" },
          { type: "hardBreak" },
          { type: "text", text: "Alpha  1" },
        ],
      },
    ]);
  });

  it("preserves leading spaces inside a verbatim table block", () => {
    const nodes = ocrReconstructionContent(
      [
        block({
          kind: "table",
          text: "  Name  Value\n  Alpha  1",
          x: 100,
          y: 100,
          width: 300,
          height: 60,
        }),
      ],
      null,
    );

    expect(nodes[0].content).toEqual([
      { type: "text", text: "  Name  Value" },
      { type: "hardBreak" },
      { type: "text", text: "  Alpha  1" },
    ]);
  });

  it("reads every paragraph in a column before moving to the next column", () => {
    const nodes = ocrReconstructionContent(
      [
        block({ text: "Left column first paragraph", x: 100, y: 100, width: 240 }),
        block({ text: "Right column first paragraph", x: 400, y: 100, width: 240 }),
        block({ text: "Left column second paragraph", x: 100, y: 200, width: 240 }),
        block({ text: "Right column second paragraph", x: 400, y: 200, width: 240 }),
      ],
      null,
    );

    expect(paragraphTexts(nodes)).toEqual([
      "Left column first paragraph",
      "Left column second paragraph",
      "Right column first paragraph",
      "Right column second paragraph",
    ]);
  });

  it("uses a full-width block to separate column bands", () => {
    const nodes = ocrReconstructionContent(
      [
        block({ text: "Left above", x: 100, y: 100, width: 240 }),
        block({ text: "Right above", x: 400, y: 100, width: 240 }),
        block({ text: "Full width separator", x: 100, y: 200, width: 540 }),
        block({ text: "Left below", x: 100, y: 300, width: 240 }),
        block({ text: "Right below", x: 400, y: 300, width: 240 }),
      ],
      null,
    );

    expect(paragraphTexts(nodes)).toEqual([
      "Left above",
      "Right above",
      "Full width separator",
      "Left below",
      "Right below",
    ]);
  });

  it("merges an indented first line into its paragraph", () => {
    const nodes = ocrReconstructionContent(
      [
        block({
          text: "The first line starts with an indent and is not finished",
          x: 136,
          y: 100,
          width: 564,
        }),
        block({
          text: "and the second line returns to the margin.",
          x: 100,
          y: 132,
          width: 600,
        }),
      ],
      null,
    );

    expect(paragraphTexts(nodes)).toEqual([
      "The first line starts with an indent and is not finished and the second line returns to the margin.",
    ]);
  });

  it("attaches an unmarked continuation line to the list item above it", () => {
    const nodes = ocrReconstructionContent(
      [
        block({
          kind: "list_item",
          text: "1. A long item that wraps",
          x: 100,
          y: 100,
          width: 400,
        }),
        block({ text: "onto a second line", x: 120, y: 132, width: 380 }),
        block({
          kind: "list_item",
          text: "2. Next item",
          x: 100,
          y: 164,
          width: 300,
        }),
      ],
      null,
    );

    expect(nodes).toHaveLength(1);
    expect(nodes[0].type).toBe("orderedList");
    expect(
      (nodes[0].content ?? []).map((item) => {
        const paragraph = item.content?.[0];
        return (paragraph?.content ?? [])
          .map((child) => ("text" in child ? (child.text ?? "") : ""))
          .join("");
      }),
    ).toEqual(["A long item that wraps onto a second line", "Next item"]);
  });

  it("keeps bullet lists in different columns separate", () => {
    const nodes = ocrReconstructionContent(
      [
        block({
          kind: "list_item",
          text: "- Left item",
          x: 100,
          y: 100,
          width: 240,
        }),
        block({
          kind: "list_item",
          text: "- Right item",
          x: 400,
          y: 100,
          width: 240,
        }),
      ],
      null,
    );

    expect(nodes.filter((node) => node.type === "bulletList")).toHaveLength(2);
  });

  it("joins Burmese lines without inserting a space", () => {
    const nodes = ocrReconstructionContent(
      [block({ text: "မြန်မာစာ\nဖတ်ရှုခြင်း" })],
      null,
    );

    expect(paragraphTexts(nodes)).toEqual(["မြန်မာစာဖတ်ရှုခြင်း"]);
  });

  it("keeps a hyphen at a line break without inventing a word", () => {
    const nodes = ocrReconstructionContent(
      [block({ text: "recon-\nstruction of text" })],
      null,
    );

    expect(paragraphTexts(nodes)).toEqual(["recon-struction of text"]);
  });

  it("joins a loose-gap continuation when the sentence is unfinished", () => {
    const nodes = ocrReconstructionContent(
      [
        block({ text: "This sentence is not finished", y: 100, height: 32 }),
        block({ text: "and continues here.", y: 160, height: 32 }),
      ],
      null,
    );

    expect(paragraphTexts(nodes)).toEqual([
      "This sentence is not finished and continues here.",
    ]);
  });

  it("does not merge a finished multi-line paragraph into the next block", () => {
    const nodes = ocrReconstructionContent(
      [
        block({
          text: "First paragraph ends here.\nSecond line of it.",
          y: 100,
          height: 64,
        }),
        block({ text: "New paragraph starts here.", y: 180, height: 32 }),
      ],
      null,
    );

    expect(paragraphTexts(nodes)).toEqual([
      "First paragraph ends here. Second line of it.",
      "New paragraph starts here.",
    ]);
  });

  it("never merges blocks that have no geometry", () => {
    const nodes = ocrReconstructionContent(
      [
        block({ text: "First part", x: null, y: null, width: null, height: null }),
        block({ text: "second part", x: null, y: null, width: null, height: null }),
      ],
      null,
    );

    expect(paragraphTexts(nodes)).toEqual(["First part", "second part"]);
  });

  it("appends the source note as a blockquote", () => {
    const nodes = ocrReconstructionContent(
      [block({ text: "Body" })],
      "Source: page 2",
    );

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

  it("returns only the note when every block is empty", () => {
    const nodes = ocrReconstructionContent(
      [block({ text: "   " })],
      "Source: page 2",
    );

    expect(nodes).toHaveLength(1);
    expect(nodes[0].type).toBe("blockquote");
  });
});
