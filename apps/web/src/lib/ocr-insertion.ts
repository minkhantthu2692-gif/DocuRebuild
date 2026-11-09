import type { JSONContent } from "@tiptap/core";

/**
 * Converts reviewed OCR text into Tiptap paragraph nodes.
 *
 * - Blank lines separate paragraphs.
 * - Single line breaks become hard breaks.
 * - Empty lines never produce empty text nodes (invalid in the schema).
 * - The optional source note is appended as a blockquote so it is visually
 *   distinct from the reconstructed content and survives export.
 */
export function ocrInsertionContent(text: string, note: string | null): JSONContent[] {
  const normalized = text.replace(/\r\n?/g, "\n");
  const nodes: JSONContent[] = normalized.split(/\n{2,}/).map((block) => {
    const content: JSONContent[] = [];
    block.split("\n").forEach((line, index) => {
      if (index > 0) content.push({ type: "hardBreak" });
      if (line) content.push({ type: "text", text: line });
    });
    return {
      type: "paragraph",
      content: content.length > 0 ? content : undefined,
    };
  });
  if (note) {
    nodes.push({
      type: "blockquote",
      content: [{ type: "paragraph", content: [{ type: "text", text: note }] }],
    });
  }
  return nodes;
}
