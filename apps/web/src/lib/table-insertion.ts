import type { JSONContent, TableAlignment } from "@docurebuild/shared-types";

/**
 * Converts a reviewed table proposal into Tiptap table nodes.
 *
 * The proposal already carries the final text, so this module never guesses a
 * value: an empty cell becomes an empty paragraph, and a cell's line breaks are
 * kept as hard breaks so a wrapped cell stays one block. Alignment is copied
 * from the proposal (or from a reviewed draft) and only centre/right needs an
 * attribute, because left is the paragraph default.
 */
export interface TableInsertionData {
  rows: string[][];
  /** Per-cell alignment; a missing or `null` value keeps the default. */
  alignments?: (TableAlignment | null)[][];
  /** Row span per anchor cell; 0 marks a coordinate covered by another cell. */
  rowSpans?: number[][];
  /** Column span per anchor cell; 0 marks a covered coordinate. */
  colSpans?: number[][];
  headerRow: boolean;
  note: string | null;
}

function paragraphFromText(
  text: string,
  alignment?: TableAlignment | null,
): JSONContent {
  const content: JSONContent[] = [];
  text.split("\n").forEach((line, index) => {
    if (index > 0) content.push({ type: "hardBreak" });
    if (line) content.push({ type: "text", text: line });
  });
  const paragraph: JSONContent = {
    type: "paragraph",
    content: content.length > 0 ? content : undefined,
  };
  if (alignment && alignment !== "left") {
    paragraph.attrs = { textAlign: alignment };
  }
  return paragraph;
}

/** Pad ragged rows so the table schema receives a rectangular grid. */
export function normalizeTableRows(rows: string[][]): string[][] {
  const columns = rows.reduce((widest, row) => Math.max(widest, row.length), 0);
  return rows.map((row) =>
    Array.from({ length: columns }, (_unused, index) => row[index] ?? ""),
  );
}

function cellSpan(
  spans: number[][] | undefined,
  row: number,
  column: number,
): number {
  return Math.max(0, Math.round(spans?.[row]?.[column] ?? 1));
}

export function tableInsertionContent(data: TableInsertionData): JSONContent[] {
  const rows = normalizeTableRows(data.rows);
  if (rows.length === 0 || (rows[0]?.length ?? 0) === 0) return [];

  const nodes: JSONContent[] = [
    {
      type: "table",
      content: rows.map((row, rowIndex) => ({
        type: "tableRow",
        content: row.flatMap((text, columnIndex) => {
          const rowSpan = cellSpan(data.rowSpans, rowIndex, columnIndex);
          const colSpan = cellSpan(data.colSpans, rowIndex, columnIndex);
          // A coordinate covered by a merged cell is not a cell of its own.
          if (rowSpan === 0 || colSpan === 0) return [];
          const node: JSONContent = {
            type: data.headerRow && rowIndex === 0 ? "tableHeader" : "tableCell",
            content: [
              paragraphFromText(text, data.alignments?.[rowIndex]?.[columnIndex]),
            ],
          };
          if (rowSpan > 1 || colSpan > 1) {
            node.attrs = { rowspan: rowSpan, colspan: colSpan };
          }
          return [node];
        }),
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
