import type { JSONContent } from "@tiptap/core";
import { describe, expect, it } from "vitest";

import {
  ocrReconstructionContent,
  type OcrReconstructionBlock,
} from "@/lib/ocr-reconstruction";

import pdfPages from "./fixtures/ocr-pdf-multipage.json";

/**
 * A real two-page PDF generated with PyMuPDF and read through
 * `services.pdf.extract_text`: page one has a title, two body paragraphs, a
 * numbered list, a two-column band and a closing paragraph; page two has a
 * heading and a paragraph. Page imports stay independent, so each page is
 * reconstructed on its own and appended in order.
 */
const [pageOne, pageTwo] = pdfPages as unknown as OcrReconstructionBlock[][];

function plainText(node: JSONContent): string {
  return (node.content ?? [])
    .map((child) => {
      if (typeof child.text === "string") return child.text;
      return plainText(child);
    })
    .join("");
}

describe("embedded PDF multi-page reconstruction", () => {
  it("reconstructs page one structure", () => {
    const nodes = ocrReconstructionContent(pageOne, null);

    expect(nodes.map((node) => node.type)).toEqual([
      "heading",
      "paragraph",
      "paragraph",
      "orderedList",
      "paragraph",
      "paragraph",
      "paragraph",
    ]);
    expect(plainText(nodes[0])).toBe("Chapter Two: Multi-page Layout");
    expect(plainText(nodes[1])).toBe(
      "This is the first paragraph on page one. It is written into a single text box and wraps across several visual lines. Reconstruction must join those lines into one editable paragraph instead of pinning each line with a hard break.",
    );
    expect(plainText(nodes[2])).toBe(
      "This second paragraph follows a clear vertical gap. It must stay separate from the paragraph above even though both use the same margins and the same body font size.",
    );
    expect((nodes[3].content ?? []).map((item) => plainText(item))).toEqual([
      "First numbered item",
      "Second numbered item",
      "Third numbered item",
    ]);
    expect(plainText(nodes[4])).toContain("The left column is its own reading stream.");
    expect(plainText(nodes[5])).toContain("The right column is a separate reading stream.");
    expect(plainText(nodes[6])).toBe(
      "A closing full-width paragraph follows the two-column band. It should join its own lines and stay separate from both columns.",
    );
  });

  it("reconstructs page two after page one", () => {
    const nodes = ocrReconstructionContent(pageTwo, null);

    expect(nodes.map((node) => node.type)).toEqual(["heading", "paragraph"]);
    expect(plainText(nodes[0])).toBe("Section Two");
    expect(plainText(nodes[1])).toBe(
      "Page two carries a second section. Its paragraph is also a single text box, and the reconstructed document should keep it after everything from page one.",
    );
  });

  it("keeps the two-column band out of the closing paragraph", () => {
    const nodes = ocrReconstructionContent(pageOne, null);
    const columns = nodes.slice(4, 6).map(plainText).join(" ");
    const closing = plainText(nodes[6]);

    expect(columns).not.toContain("closing full-width paragraph");
    expect(closing).not.toContain("left column");
  });
});
