import { Editor } from "@tiptap/core";
import { afterEach, describe, expect, it } from "vitest";

import { createEditorExtensions } from "@/lib/editor-extensions";
import {
  equationAt,
  equationContent,
  renderEquationPreview,
  selectedEquation,
} from "@/lib/editor-equation";

let editor: Editor | null = null;

afterEach(() => {
  editor?.destroy();
  editor = null;
});

function createEditor(): Editor {
  return new Editor({
    extensions: createEditorExtensions(() => "Start writing"),
    content: { type: "doc", content: [{ type: "paragraph" }] },
  });
}

function insertEquation(instance: Editor, latex: string): number {
  instance.commands.insertContent(equationContent(latex));
  let pos = -1;
  instance.state.doc.descendants((node, nodePos) => {
    if (node.type.name === "blockMath") pos = nodePos;
  });
  return pos;
}

describe("equation editor node", () => {
  it("stores the LaTeX source without rendering it into the document", () => {
    editor = createEditor();
    insertEquation(editor, "E = mc^2");

    const equation = editor.getJSON().content?.find((node) => node.type === "blockMath");
    expect(equation?.attrs).toMatchObject({ latex: "E = mc^2" });

    const html = editor.getHTML();
    expect(html).toContain('data-type="block-math"');
    expect(html).toContain('data-latex="E = mc^2"');
    // The saved document holds source only; KaTeX markup is rendered at view time.
    expect(html).not.toContain("katex");
  });

  it("finds an equation only when the whole node is selected", () => {
    editor = createEditor();
    const pos = insertEquation(editor, "a^2 + b^2 = c^2");

    editor.commands.setTextSelection(1);
    expect(selectedEquation(editor.state)).toBeNull();

    editor.commands.setNodeSelection(pos);
    expect(selectedEquation(editor.state)).toEqual({
      pos,
      latex: "a^2 + b^2 = c^2",
    });
  });

  it("reads by stored position and rejects stale or out-of-range positions", () => {
    editor = createEditor();
    const pos = insertEquation(editor, "\\sum_{i=1}^{n} x_i");

    expect(equationAt(editor.state, pos)?.latex).toBe("\\sum_{i=1}^{n} x_i");
    expect(equationAt(editor.state, 1)).toBeNull();
    expect(equationAt(editor.state, 9999)).toBeNull();

    editor.commands.clearContent();
    expect(equationAt(editor.state, pos)).toBeNull();
  });

  it("updates the LaTeX source and keeps the node type", () => {
    editor = createEditor();
    const pos = insertEquation(editor, "x");

    editor
      .chain()
      .setNodeSelection(pos)
      .updateBlockMath({ latex: "\\int_0^1 x^2\\,dx" })
      .run();

    const equation = editor.getJSON().content?.find((node) => node.type === "blockMath");
    expect(equation?.attrs).toMatchObject({ latex: "\\int_0^1 x^2\\,dx" });
  });

  it("previews valid LaTeX locally and rejects invalid source", () => {
    const valid = renderEquationPreview("\\frac{a}{b}");
    expect(valid.error).toBe(false);
    expect(valid.html).toContain("katex");

    const blank = renderEquationPreview("   ");
    expect(blank).toEqual({ html: null, error: false });

    const invalid = renderEquationPreview("\\frac{");
    expect(invalid).toEqual({ html: null, error: true });
  });
});
