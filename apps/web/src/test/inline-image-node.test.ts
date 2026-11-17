import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { afterEach, describe, expect, it } from "vitest";

import type { JSONContent } from "@docurebuild/shared-types";

import {
  InlineImageNode,
  inlineImageInsertionContent,
} from "@/lib/editor-inline-image";

let editor: Editor | null = null;

afterEach(() => {
  editor?.destroy();
  editor = null;
});

function createEditor(content?: unknown): Editor {
  return new Editor({
    extensions: [StarterKit, InlineImageNode],
    content:
      content ??
      ({
        type: "doc",
        content: [
          {
            type: "paragraph",
            content: [{ type: "text", text: "The state " }],
          },
        ],
      } as never),
  });
}

function docJson(instance: Editor): JSONContent {
  return instance.getJSON() as JSONContent;
}

function paragraphChildren(instance: Editor): JSONContent[] {
  return docJson(instance).content?.[0]?.content ?? [];
}

describe("inlineImageInsertionContent", () => {
  it("is a single inline node that stores only src and alt", () => {
    const nodes = inlineImageInsertionContent({
      src: "/api/projects/p/assets/a/file",
      alt: "Wave function",
    });

    expect(nodes).toHaveLength(1);
    expect(nodes[0]).toEqual({
      type: "inlineImage",
      attrs: { src: "/api/projects/p/assets/a/file", alt: "Wave function" },
    });
  });
});

describe("inline image editor node", () => {
  it("stays inside the sentence instead of breaking the paragraph", () => {
    editor = createEditor();
    // Put the cursor after the existing text, as in real typing.
    editor.commands.setTextSelection(editor.state.doc.content.size - 1);
    editor.commands.insertContent(
      inlineImageInsertionContent({ src: "/file", alt: "Wave function" }),
    );
    editor.commands.insertContent(" and momentum.");

    const doc = docJson(editor);
    expect(doc.content).toHaveLength(1);
    const paragraph = doc.content?.[0];
    expect(paragraph?.type).toBe("paragraph");
    expect(paragraph?.content?.map((node) => node.type)).toEqual([
      "text",
      "inlineImage",
      "text",
    ]);
    expect(paragraph?.content?.[1]?.attrs).toEqual({
      src: "/file",
      alt: "Wave function",
    });
  });

  it("renders an accessible picture with the inline style hook", () => {
    editor = createEditor();
    editor.commands.insertContent(
      inlineImageInsertionContent({ src: "/file", alt: "Wave function" }),
    );

    const html = editor.getHTML();
    expect(html).toContain('class="doc-inline-image"');
    expect(html).toContain("data-doc-inline-image");
    expect(html).toContain('alt="Wave function"');
    // Caption, note and figure numbering belong to the block figure node.
    expect(html).not.toContain("caption");
    expect(html).not.toContain("numbered");
  });

  it("keeps the alt text empty when it is unknown instead of inventing one", () => {
    editor = createEditor();
    editor.commands.insertContent(
      inlineImageInsertionContent({ src: "/file", alt: "" }),
    );

    expect(editor.getHTML()).toContain('alt=""');
    const inline = paragraphChildren(editor).find(
      (node) => node.type === "inlineImage",
    );
    expect(inline?.attrs?.alt).toBe("");
  });

  it("deletes exactly one picture and leaves the text intact", () => {
    editor = createEditor();
    editor.commands.insertContent(
      inlineImageInsertionContent({ src: "/first", alt: "One" }),
    );
    editor.commands.insertContent(" between ");
    editor.commands.insertContent(
      inlineImageInsertionContent({ src: "/second", alt: "Two" }),
    );
    editor.commands.insertContent(" after.");

    let inlinePos = -1;
    editor.state.doc.descendants((node, pos) => {
      if (node.type.name === "inlineImage" && node.attrs.src === "/first") {
        inlinePos = pos;
      }
    });
    expect(inlinePos).toBeGreaterThanOrEqual(0);

    editor.chain().setNodeSelection(inlinePos).deleteSelection().run();

    const remaining = paragraphChildren(editor).filter(
      (node) => node.type === "inlineImage",
    );
    expect(remaining).toHaveLength(1);
    expect(remaining[0]?.attrs?.src).toBe("/second");
    expect(editor.getText()).toContain("between");
    expect(editor.getText()).toContain("after.");
  });

  it("parses its own exported HTML back into the same node", () => {
    editor = createEditor();
    editor.commands.insertContent(
      inlineImageInsertionContent({ src: "/file", alt: "Diagram" }),
    );
    const html = editor.getHTML();

    editor.destroy();
    editor = createEditor(html);

    const inline = paragraphChildren(editor).find(
      (node) => node.type === "inlineImage",
    );
    expect(inline?.attrs).toEqual({ src: "/file", alt: "Diagram" });
  });
});
