import type { JSONContent } from "@tiptap/core";

import { equationContent } from "./editor-equation";

export interface FormulaInsertionData {
  /** Reviewed LaTeX source. It is stored as-is and never rewritten. */
  latex: string;
  numbered: boolean;
  note: string | null;
}

/**
 * Converts a reviewed formula from an extracted region into a display equation.
 *
 * Only the LaTeX the user confirmed is written; nothing is inferred from the
 * crop. The optional source note reuses the blockquote used by extracted text, so
 * a reconstructed equation is never presented as if the document already held it.
 */
export function formulaInsertionContent(data: FormulaInsertionData): JSONContent[] {
  const nodes: JSONContent[] = [equationContent(data.latex.trim(), "block", data.numbered)];
  if (data.note) {
    nodes.push({
      type: "blockquote",
      content: [{ type: "paragraph", content: [{ type: "text", text: data.note }] }],
    });
  }
  return nodes;
}
