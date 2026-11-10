import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { afterEach, describe, expect, it } from "vitest";

import { FigureNode, figureInsertionContent } from "@/lib/editor-figure";

let editor: Editor | null = null;

afterEach(() => {
  editor?.destroy();
  editor = null;
});

describe("figure editor node", () => {
  it("stores and renders an inserted region with its caption and source note", () => {
    editor = new Editor({
      extensions: [StarterKit, FigureNode],
      content: { type: "doc", content: [{ type: "paragraph" }] },
    });

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
});
