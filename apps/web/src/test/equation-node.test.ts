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

function findNodePos(instance: Editor, name: string): number {
  let pos = -1;
  instance.state.doc.descendants((node, nodePos) => {
    if (node.type.name === name) pos = nodePos;
  });
  return pos;
}

function insertEquation(instance: Editor, latex: string, kind: "block" | "inline" = "block"): number {
  instance.commands.insertContent(equationContent(latex, kind));
  return findNodePos(instance, kind === "inline" ? "inlineMath" : "blockMath");
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
      kind: "block",
      numbered: false,
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

  it("stores an optional number flag and marks the equation in the editor", () => {
    editor = createEditor();
    editor.commands.insertContent(equationContent("a = b", "block", true));

    const equation = editor.getJSON().content?.find((node) => node.type === "blockMath");
    expect(equation?.attrs).toMatchObject({ latex: "a = b", numbered: true });

    // The flag is part of the saved document, the number itself never is.
    const html = editor.getHTML();
    expect(html).toContain('data-numbered="true"');
    expect(html).not.toContain("(1)");

    const nodeView = editor.view.dom.querySelector(
      '[data-type="block-math"]',
    ) as HTMLElement | null;
    expect(nodeView?.classList.contains("numbered-equation")).toBe(true);
    expect(nodeView?.dataset.numbered).toBe("true");
  });

  it("leaves an unnumbered equation unmarked", () => {
    editor = createEditor();
    editor.commands.insertContent(equationContent("a = b"));

    const doc = editor.getJSON();
    const block = doc.content?.find((node) => node.type === "blockMath");
    expect(block?.attrs).toMatchObject({ latex: "a = b", numbered: false });

    expect(editor.getHTML()).not.toContain('data-numbered="true"');
    expect(
      editor.view.dom.querySelectorAll(".numbered-equation"),
    ).toHaveLength(0);
  });

  it("never numbers inline math", () => {
    editor = createEditor();
    editor.commands.insertContent(equationContent("x^2", "inline", true));

    const inlinePos = findNodePos(editor, "inlineMath");
    expect(equationAt(editor.state, inlinePos)).toEqual({
      pos: inlinePos,
      latex: "x^2",
      kind: "inline",
      numbered: false,
    });
    expect(JSON.stringify(editor.getJSON())).not.toContain('"numbered":true');
    expect(editor.getHTML()).not.toContain('data-numbered="true"');
  });

  it("toggles the number on an existing display equation", () => {
    editor = createEditor();
    const pos = insertEquation(editor, "x = 1");

    const setNumbered = (numbered: boolean) => {
      editor
        ?.chain()
        .command(({ tr }) => {
          const node = tr.doc.nodeAt(pos);
          if (!node || node.type.name !== "blockMath") return false;
          tr.setNodeMarkup(pos, undefined, { ...node.attrs, numbered });
          return true;
        })
        .run();
    };

    setNumbered(true);
    expect(equationAt(editor.state, pos)?.numbered).toBe(true);
    expect(
      (editor.view.dom.querySelector('[data-type="block-math"]') as HTMLElement)
        .classList.contains("numbered-equation"),
    ).toBe(true);

    setNumbered(false);
    expect(equationAt(editor.state, pos)?.numbered).toBe(false);
    expect(
      (editor.view.dom.querySelector('[data-type="block-math"]') as HTMLElement)
        .classList.contains("numbered-equation"),
    ).toBe(false);
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

  it("inserts inline math inside a paragraph without dropping the text", () => {
    editor = createEditor();
    editor.commands.insertContent("Energy ");
    const pos = insertEquation(editor, "E = mc^2", "inline");
    editor.commands.insertContent(" and momentum.");

    const paragraph = editor.getJSON().content?.[0];
    expect(paragraph?.content?.map((node) => node.type)).toEqual([
      "text",
      "inlineMath",
      "text",
    ]);
    expect(paragraph?.content?.[1]).toMatchObject({
      type: "inlineMath",
      attrs: { latex: "E = mc^2" },
    });

    // Inline math stays inside the paragraph and is saved as source only.
    expect(equationAt(editor.state, pos)).toEqual({
      pos,
      latex: "E = mc^2",
      kind: "inline",
      numbered: false,
    });
    const html = editor.getHTML();
    expect(html).toContain('data-type="inline-math"');
    expect(html).not.toContain("katex");
  });

  it("updates an inline formula in place", () => {
    editor = createEditor();
    const pos = insertEquation(editor, "x", "inline");

    editor
      .chain()
      .setNodeSelection(pos)
      .updateInlineMath({ latex: "x^2", pos })
      .run();

    expect(equationAt(editor.state, pos)).toEqual({
      pos,
      latex: "x^2",
      kind: "inline",
      numbered: false,
    });
    expect(editor.state.doc.textContent).toBe("");
  });

  it("previews inline math without display spacing", () => {
    const block = renderEquationPreview("x^2");
    const inline = renderEquationPreview("x^2", "inline");

    expect(block.html).toContain("katex-display");
    expect(inline.error).toBe(false);
    expect(inline.html).toContain("katex");
    expect(inline.html).not.toContain("katex-display");
  });

  it("does not convert typed prose into inline math automatically", () => {
    editor = createEditor();
    const extension = editor.extensionManager.extensions.find(
      (item) => item.name === "inlineMath",
    ) as { config: { addInputRules?: () => unknown[] } } | undefined;

    expect(extension).toBeDefined();
    // The dialog is the only way in: no `$$...$$` input rule rewrites prose.
    expect(extension?.config.addInputRules?.()).toEqual([]);
  });
});
