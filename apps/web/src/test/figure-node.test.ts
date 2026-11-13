import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { afterEach, describe, expect, it } from "vitest";

import {
  FigureNode,
  figureAt,
  figureInsertionContent,
  selectedFigure,
} from "@/lib/editor-figure";

let editor: Editor | null = null;

afterEach(() => {
  editor?.destroy();
  editor = null;
});

function createEditor(): Editor {
  return new Editor({
    extensions: [StarterKit, FigureNode],
    content: { type: "doc", content: [{ type: "paragraph" }] },
  });
}

function insertFigure(instance: Editor): number {
  instance.commands.insertContent(
    figureInsertionContent({
      src: "/api/projects/p/assets/a/file",
      alt: "Figure 1",
      caption: "Figure 1. Phase diagram",
      note: "Source: page 4 · manual region · Unverified",
      width: 320,
      height: 180,
    }),
  );
  let pos = -1;
  instance.state.doc.descendants((node, nodePos) => {
    if (node.type.name === "figure") pos = nodePos;
  });
  return pos;
}

describe("figure editor node", () => {
  it("stores and renders an inserted region with its caption and source note", () => {
    editor = createEditor();

    editor.commands.insertContent(
      figureInsertionContent({
        src: "/api/projects/p/assets/a/file",
        alt: "Figure 1",
        caption: "Figure 1. Phase diagram",
        note: "Source: page 4 · manual region · Unverified",
        width: 320,
        height: 180,
      }),
    );

    const figure = editor
      .getJSON()
      .content?.find((node) => node.type === "figure");
    expect(figure?.attrs).toMatchObject({
      src: "/api/projects/p/assets/a/file",
      alt: "Figure 1",
      caption: "Figure 1. Phase diagram",
      width: 320,
      height: 180,
    });

    const html = editor.getHTML();
    expect(html).toContain("<figure");
    expect(html).toContain('data-doc-figure=""');
    expect(html).toContain("Figure 1. Phase diagram");
    expect(html).toContain("Source: page 4 · manual region · Unverified");
  });

  it("finds a figure only when the whole node is selected", () => {
    editor = createEditor();
    const pos = insertFigure(editor);
    const id = editor
      .getJSON()
      .content?.find((node) => node.type === "figure")?.attrs?.id;
    expect(typeof id).toBe("string");

    // Inserting the figure leaves it selected, so it can be edited right away.
    expect(selectedFigure(editor.state)).toEqual({
      pos,
      id,
      caption: "Figure 1. Phase diagram",
      alt: "Figure 1",
      note: "Source: page 4 · manual region · Unverified",
      numbered: false,
    });

    editor.commands.setTextSelection(1);
    expect(selectedFigure(editor.state)).toBeNull();

    editor.commands.setNodeSelection(pos);
    expect(selectedFigure(editor.state)?.caption).toBe("Figure 1. Phase diagram");
  });

  it("reads a figure by stored position and rejects stale positions", () => {
    editor = createEditor();
    const pos = insertFigure(editor);
    expect(figureAt(editor.state, pos)?.caption).toBe("Figure 1. Phase diagram");

    // A text position and an out-of-range position are not figures.
    expect(figureAt(editor.state, 1)).toBeNull();
    expect(figureAt(editor.state, 9999)).toBeNull();

    // Replacing the document invalidates the stored position.
    editor.commands.clearContent();
    expect(figureAt(editor.state, pos)).toBeNull();
  });

  it("corrects the caption and alt text without changing the image or note", () => {
    editor = createEditor();
    const pos = insertFigure(editor);

    editor
      .chain()
      .setNodeSelection(pos)
      .updateAttributes("figure", {
        caption: "Figure 1. Corrected phase diagram",
        alt: "Phase diagram of the alloy",
      })
      .run();

    const figure = editor
      .getJSON()
      .content?.find((node) => node.type === "figure");
    expect(figure?.attrs).toMatchObject({
      src: "/api/projects/p/assets/a/file",
      caption: "Figure 1. Corrected phase diagram",
      alt: "Phase diagram of the alloy",
      note: "Source: page 4 · manual region · Unverified",
      width: 320,
      height: 180,
    });

    const html = editor.getHTML();
    expect(html).toContain("Corrected phase diagram");
    expect(html).not.toContain("Figure 1. Phase diagram");
    expect(html).toContain('alt="Phase diagram of the alloy"');
    expect(html).toContain("Unverified");
  });

  it("stores an optional figure number without rewriting the caption", () => {
    editor = createEditor();
    editor.commands.insertContent(
      figureInsertionContent({
        src: "/api/projects/p/assets/a/file",
        alt: "Phase diagram",
        caption: "Phase diagram",
        note: "Source: page 4",
        width: 320,
        height: 180,
        numbered: true,
      }),
    );

    const figure = editor
      .getJSON()
      .content?.find((node) => node.type === "figure");
    expect(figure?.attrs).toMatchObject({ caption: "Phase diagram", numbered: true });

    const html = editor.getHTML();
    expect(html).toContain('data-numbered="true"');
    expect(html).toContain("data-figure-label");
    // The label is CSS-generated chrome, so no number is written into the caption.
    expect(html).toContain("Phase diagram");
    expect(html).not.toContain("Figure 1. Phase diagram");

    // The flag survives an HTML round-trip, so a saved document keeps it.
    editor.commands.setContent(html);
    const restored = editor
      .getJSON()
      .content?.find((node) => node.type === "figure");
    expect(restored?.attrs).toMatchObject({ caption: "Phase diagram", numbered: true });
  });

  it("leaves an unnumbered figure without number markup", () => {
    editor = createEditor();
    insertFigure(editor);

    const html = editor.getHTML();
    expect(html).not.toContain('data-numbered="true"');
    expect(html).not.toContain("data-figure-label");
  });
});
