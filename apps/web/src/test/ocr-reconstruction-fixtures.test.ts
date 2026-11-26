import type { JSONContent } from "@tiptap/core";
import { describe, expect, it } from "vitest";

import {
  ocrReconstructionContent,
  type OcrReconstructionBlock,
} from "@/lib/ocr-reconstruction";

import psm3 from "./fixtures/ocr-page-psm3.json";
import psm11 from "./fixtures/ocr-page-psm11.json";

/**
 * These fixtures are the stored blocks for one synthetic A4 page captured from
 * Tesseract 5 with PSM 3 (automatic layout) and PSM 11 (sparse text). The page
 * holds a title, two body paragraphs, a numbered list, a two-column band and a
 * closing paragraph. PSM 3 emits multi-line blocks and merges the columns; PSM
 * 11 emits one block per visual line. Both must reconstruct to the same
 * document.
 */
const fixtures: [string, OcrReconstructionBlock[]][] = [
  ["PSM 3", psm3 as unknown as OcrReconstructionBlock[]],
  ["PSM 11", psm11 as unknown as OcrReconstructionBlock[]],
];

const expectedParagraphs = [
  "This is the first paragraph of the document. It contains several sentences that should flow together as one continuous block of text when the page is reconstructed in the editor, rather than becoming one paragraph per line.",
  "This is the second paragraph. It starts after a clear vertical gap and has its own first line. It should remain separate from the paragraph above even though both paragraphs share the same left and right margins.",
  "The left column contains a short paragraph that must not be merged with the right column even though the lines are close together vertically.",
  "The right column is a separate reading stream. Column-aware reconstruction keeps its lines together and in order.",
  "A final full-width paragraph closes the page. It should join the lines above into a single editable paragraph with normal wrapping.",
];

function listItemTexts(node: JSONContent): string[] {
  return (node.content ?? []).map((item) => {
    const paragraph = item.content?.[0];
    return (paragraph?.content ?? [])
      .map((child) => ("text" in child ? (child.text ?? "") : ""))
      .join("");
  });
}

describe.each(fixtures)("real Tesseract page reconstruction (%s)", (_label, blocks) => {
  const nodes = ocrReconstructionContent(blocks, null);

  it("keeps the document structure", () => {
    expect(nodes.map((node) => node.type)).toEqual([
      "heading",
      "paragraph",
      "paragraph",
      "orderedList",
      "paragraph",
      "paragraph",
      "paragraph",
    ]);
  });

  it("joins wrapped lines into flowing paragraphs", () => {
    const paragraphs = nodes
      .filter((node) => node.type === "paragraph")
      .map((node) =>
        (node.content ?? [])
          .map((child) => ("text" in child ? (child.text ?? "") : ""))
          .join(""),
      );
    expect(paragraphs).toEqual(expectedParagraphs);
    expect(JSON.stringify(nodes)).not.toContain("hardBreak");
  });

  it("keeps the numbered list as list items", () => {
    const list = nodes[3];
    expect(list.type).toBe("orderedList");
    expect(listItemTexts(list)).toEqual([
      "First numbered item",
      "Second numbered item",
      "Third numbered item",
    ]);
  });

  it("keeps the two columns apart and in reading order", () => {
    const paragraphs = nodes.filter((node) => node.type === "paragraph");
    const left = (paragraphs[2].content ?? [])
      .map((child) => ("text" in child ? (child.text ?? "") : ""))
      .join("");
    const right = (paragraphs[3].content ?? [])
      .map((child) => ("text" in child ? (child.text ?? "") : ""))
      .join("");
    expect(left).toContain("The left column");
    expect(left).toContain("close together vertically.");
    expect(right).toContain("The right column");
    expect(right).toContain("keeps its lines together and in order.");
  });
});

describe("Tesseract segmentation modes agree", () => {
  it("produces the same document from PSM 3 and PSM 11 blocks", () => {
    const automatic = ocrReconstructionContent(
      psm3 as unknown as OcrReconstructionBlock[],
      null,
    );
    const sparse = ocrReconstructionContent(
      psm11 as unknown as OcrReconstructionBlock[],
      null,
    );
    expect(sparse).toEqual(automatic);
  });
});
