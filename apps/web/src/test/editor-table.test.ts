import { Editor, type Content } from "@tiptap/core";
import { afterEach, describe, expect, it } from "vitest";

import type { JSONContent } from "@docurebuild/shared-types";

import { createEditorExtensions } from "@/lib/editor-extensions";
import {
  TABLE_MAX_SIZE,
  TABLE_MIN_SIZE,
  clampTableSize,
  tableInsertOptions,
} from "@/lib/editor-table";

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

describe("manual table editing", () => {
  it("inserts an empty table with the requested header row", () => {
    const instance = createEditor();
    instance.commands.insertTable(tableInsertOptions(3, 4, true));

    const table = documentJSON(instance).content?.find((node) => node.type === "table");
    const rows = table?.content ?? [];
    expect(rows).toHaveLength(3);
    expect(rows[0]?.content).toHaveLength(4);
    expect(rows[0]?.content?.every((cell) => cell.type === "tableHeader")).toBe(true);
    expect(rows[1]?.content?.every((cell) => cell.type === "tableCell")).toBe(true);
    // Manual path only: a new table never contains invented cell text.
    expect(instance.getText().trim()).toBe("");
  });

  it("inserts a table without a header when asked", () => {
    const instance = createEditor();
    instance.commands.insertTable(tableInsertOptions(2, 2, false));

    const table = documentJSON(instance).content?.find((node) => node.type === "table");
    const rows = table?.content ?? [];
    expect(rows).toHaveLength(2);
    expect(rows[0]?.content?.every((cell) => cell.type === "tableCell")).toBe(true);
  });

  it("keeps typed cell text through a JSON round trip", () => {
    const instance = createEditor();
    instance.commands.insertTable(tableInsertOptions(2, 2, true));
    instance.commands.insertContent("Mass");

    const json = documentJSON(instance);
    expect(JSON.stringify(json)).toContain('"text":"Mass"');

    const copy = new Editor({
      extensions: createEditorExtensions(() => ""),
      content: json as unknown as Content,
    });
    try {
      expect(copy.getText()).toContain("Mass");
    } finally {
      copy.destroy();
    }
  });

  it("adds and deletes rows and columns of an existing table", () => {
    const instance = createEditor();
    instance.commands.insertTable(tableInsertOptions(2, 2, true));

    instance.commands.addRowAfter();
    instance.commands.addColumnAfter();
    let table = documentJSON(instance).content?.find((node) => node.type === "table");
    expect(table?.content).toHaveLength(3);
    expect(table?.content?.[0]?.content).toHaveLength(3);

    instance.commands.deleteRow();
    instance.commands.deleteColumn();
    table = documentJSON(instance).content?.find((node) => node.type === "table");
    expect(table?.content).toHaveLength(2);
    expect(table?.content?.[0]?.content).toHaveLength(2);
  });

  it("clamps table sizes to the supported bounds", () => {
    expect(clampTableSize(0)).toBe(TABLE_MIN_SIZE);
    expect(clampTableSize(Number.NaN)).toBe(TABLE_MIN_SIZE);
    expect(clampTableSize(999)).toBe(TABLE_MAX_SIZE);
    expect(clampTableSize(4.9)).toBe(4);
    expect(tableInsertOptions(0, 99, false)).toEqual({
      rows: TABLE_MIN_SIZE,
      cols: TABLE_MAX_SIZE,
      withHeaderRow: false,
    });
  });
});

