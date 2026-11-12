import type { Node as ProseMirrorNode } from "@tiptap/pm/model";

export interface EditorMatch {
  from: number;
  to: number;
}

/**
 * Find plain-text matches in a ProseMirror document.
 *
 * Matches may span inline marks (a bold word is still one word) but never cross
 * a block or hard-break boundary, so a query cannot silently match two
 * unrelated paragraphs. Positions are real document positions and can be used
 * with `setTextSelection` or a transaction.
 */
export function findMatches(
  doc: ProseMirrorNode,
  query: string,
  matchCase = false,
): EditorMatch[] {
  if (!query) return [];
  const matches: EditorMatch[] = [];
  // A regex keeps case folding Unicode-safe: lowercasing a string can change
  // its length and shift every following position.
  const pattern = new RegExp(
    query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
    matchCase ? "g" : "gi",
  );

  let runStart: number | null = null;
  let buffer = "";

  const flush = () => {
    if (runStart !== null && buffer) {
      pattern.lastIndex = 0;
      let match = pattern.exec(buffer);
      while (match !== null) {
        matches.push({
          from: runStart + match.index,
          to: runStart + match.index + match[0].length,
        });
        if (match[0].length === 0) pattern.lastIndex += 1;
        match = pattern.exec(buffer);
      }
    }
    runStart = null;
    buffer = "";
  };

  doc.descendants((node, pos) => {
    if (node.isText) {
      const text = node.text ?? "";
      if (!text) return false;
      // Contiguous text nodes keep their marks but share one position run.
      if (runStart !== null && pos !== runStart + buffer.length) flush();
      if (runStart === null) runStart = pos;
      buffer += text;
      return false;
    }
    // Any non-text node (block, hard break, figure) ends the current run.
    flush();
    return true;
  });
  flush();

  return matches;
}
