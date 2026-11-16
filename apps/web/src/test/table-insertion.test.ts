import { Editor, type Content } from "@tiptap/core";
import { afterEach, describe, expect, it } from "vitest";

import type { JSONContent } from "@docurebuild/shared-types";

import { createEditorExtensions } from "@/lib/editor-extensions";
import { normalizeTableRows, tableInsertionContent } from "@/lib/table-insertion";

let editor: Editor | null = null;

afterEach(() => {
  editor?.destroy();
  editor = null;
});

function createEditor(): Editor {
  editor = new Editor({
    extensions: createEditorExtensions(() => "Type"),
    content: { type: "doc", content: [{ type: "paragraph" }] },
  });
  return editor;
}

function documentJSON(instance: Editor): JSONContent {
  return instance.getJSON() as unknown as JSONContent;
}

describe("tableInsertionContent", () => {
  it("pads ragged rows so the schema receives a rectangle", () => {
    expect(normalizeTableRows([["A", "B"], ["C"], []])).toEqual([
      ["A", "B"],
      ["C", ""],
      ["", ""],
    ]);
  });

  it("builds a header row and keeps empty cells empty", () => {
    const [table] = tableInsertionContent({
      rows: [
        ["Name", "Value"],
        ["Mass"],
      ],
      headerRow: true,
      note: null,
    });

    expect(table.type).toBe("table");
    const rows = table.content ?? [];
    expect(rows).toHaveLength(2);
    expect(rows[0]?.content?.map((cell) => cell.type)).toEqual([
      "tableHeader",
      "tableHeader",
    ]);
    expect(rows[1]?.content?.map((cell) => cell.type)).toEqual([
      "tableCell",
      "tableCell",
    ]);
    const emptyCell = rows[1]?.content?.[1];
    expect(emptyCell?.content?.[0]?.content).toBeUndefined();
  });

  it("keeps line breaks inside one cell", () => {
    const [table] = tableInsertionContent({
      rows: [["First\nSecond"]],
      headerRow: false,
      note: null,
    });
    const paragraph = table.content?.[0]?.content?.[0]?.content?.[0];
    expect(paragraph?.content?.map((node) => node.type)).toEqual([
      "text",
      "hardBreak",
      "text",
    ]);
  });

  it("appends the source note as a separate blockquote", () => {
    const nodes = tableInsertionContent({
      rows: [["A"]],
      headerRow: false,
      note: "Source: page 2",
    });
    expect(nodes).toHaveLength(2);
    expect(nodes[1]?.type).toBe("blockquote");
    expect(nodes[1]?.content?.[0]?.content?.[0]?.text).toBe("Source: page 2");
  });

  it("applies only the alignments the proposal observed", () => {
    const [table] = tableInsertionContent({
      rows: [
        ["Name", "Value"],
        ["Mass", "2"],
      ],
      alignments: [
        ["left", "center"],
        [null, "right"],
      ],
      headerRow: false,
      note: null,
    });
    const paragraphs = (table.content ?? []).map((row) =>
      (row.content ?? []).map((cell) => cell.content?.[0]),
    );

    // Left is the paragraph default, so it needs no attribute; a coordinate the
    // proposal did not include must not receive an invented alignment.
    expect(paragraphs[0]?.[0]?.attrs).toBeUndefined();
    expect(paragraphs[0]?.[1]?.attrs).toEqual({ textAlign: "center" });
    expect(paragraphs[1]?.[0]?.attrs).toBeUndefined();
    expect(paragraphs[1]?.[1]?.attrs).toEqual({ textAlign: "right" });
  });

  it("keeps cell alignment in the real editor schema", () => {
    const instance = createEditor();
    instance.commands.insertContent(
      tableInsertionContent({
        rows: [["Name", "Value"]],
        alignments: [["left", "center"]],
        headerRow: false,
        note: null,
      }) as Content,
    );

    const table = documentJSON(instance).content?.find((node) => node.type === "table");
    const cells = table?.content?.[0]?.content ?? [];
    expect(cells[0]?.content?.[0]?.attrs?.textAlign ?? null).toBeNull();
    expect(cells[1]?.content?.[0]?.attrs?.textAlign).toBe("center");
  });

  it("inserts into the real editor schema", () => {
    const instance = createEditor();
    instance.commands.insertContent(
      tableInsertionContent({
        rows: [
          ["Name", "Value"],
          ["Mass", "2"],
        ],
        headerRow: true,
        note: null,
      }) as Content,
    );

    const table = documentJSON(instance).content?.find((node) => node.type === "table");
    expect(table?.content).toHaveLength(2);
    expect(table?.content?.[0]?.content).toHaveLength(2);
    expect(instance.getText()).toContain("Mass");
    expect(instance.getText()).toContain("2");
  });
});
