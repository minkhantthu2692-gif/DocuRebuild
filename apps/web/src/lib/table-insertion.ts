import type { JSONContent } from "@docurebuild/shared-types";

/**
 * Converts a reviewed table proposal into Tiptap table nodes.
 *
 * The proposal already carries the final text, so this module never guesses a
 * value: an empty cell becomes an empty paragraph, and a cell's line breaks are
 * kept as hard breaks so a wrapped cell stays one block.
 */
export interface TableInsertionData {
  rows: string[][];
  headerRow: boolean;
  note: string | null;
}

function paragraphFromText(text: string): JSONContent {
  const content: JSONContent[] = [];
  text.split("\n").forEach((line, index) => {
    if (index > 0) content.push({ type: "hardBreak" });
    if (line) content.push({ type: "text", text: line });
  });
  return {
    type: "paragraph",
    content: content.length > 0 ? content : undefined,
  };
}

/** Pad ragged rows so the table schema receives a rectangular grid. */
export function normalizeTableRows(rows: string[][]): string[][] {
  const columns = rows.reduce((widest, row) => Math.max(widest, row.length), 0);
  return rows.map((row) =>
    Array.from({ length: columns }, (_unused, index) => row[index] ?? ""),
  );
}

export function tableInsertionContent(data: TableInsertionData): JSONContent[] {
  const rows = normalizeTableRows(data.rows);
  if (rows.length === 0 || (rows[0]?.length ?? 0) === 0) return [];

  const nodes: JSONContent[] = [
    {
      type: "table",
      content: rows.map((row, rowIndex) => ({
        type: "tableRow",
        content: row.map((text) => ({
          type: data.headerRow && rowIndex === 0 ? "tableHeader" : "tableCell",
          content: [paragraphFromText(text)],
        })),
      })),
    },
  ];

  if (data.note) {
    nodes.push({
      type: "blockquote",
      content: [
        {
          type: "paragraph",
          content: [{ type: "text", text: data.note }],
        },
      ],
    });
  }
  return nodes;
}
