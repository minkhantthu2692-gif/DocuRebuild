import type { JSONContent } from "@tiptap/core";
import { Editor } from "@tiptap/core";
import { afterEach, describe, expect, it } from "vitest";

import { createEditorExtensions } from "@/lib/editor-extensions";
import {
  ocrReconstructionContent,
  type OcrReconstructionBlock,
} from "@/lib/ocr-reconstruction";

import psm3 from "./fixtures/ocr-page-psm3.json";

/**
 * End-to-end check of the insertion path: reconstruct real Tesseract blocks and
 * insert them into the real editor extension set, then verify that the document
 * reflows and accepts Justify. The unit tests cover the node tree; this test
 * covers what the editor actually stores.
 */
const blocks = psm3 as unknown as OcrReconstructionBlock[];

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

function insertReconstruction(instance: Editor): void {
  instance
    .chain()
    .focus("end")
    .insertContent(ocrReconstructionContent(blocks, null))
    .run();
}

function topLevelNodes(instance: Editor): JSONContent[] {
  return (instance.getJSON().content ?? []).filter(
    (node) =>
      node.type !== "paragraph" || (node.content ?? []).length > 0,
  );
}

function nodeText(node: JSONContent): string {
  return (node.content ?? [])
    .map((child) =>
      "text" in child ? (child.text ?? "") : nodeText(child),
    )
    .join("");
}

function paragraphTexts(instance: Editor): string[] {
  const texts: string[] = [];
  instance.state.doc.descendants((node) => {
    if (node.type.name === "paragraph") texts.push(node.textContent);
    return true;
  });
  return texts;
}

describe("OCR reconstruction in the editor", () => {
  it("inserts flowing paragraphs instead of hard-broken lines", () => {
    editor = createEditor();
    insertReconstruction(editor);

    const nodes = topLevelNodes(editor);
    expect(nodes.map((node) => node.type)).toEqual([
      "heading",
      "paragraph",
      "paragraph",
      "orderedList",
      "paragraph",
      "paragraph",
      "paragraph",
    ]);
    expect(JSON.stringify(editor.getJSON())).not.toContain("hardBreak");
    expect(paragraphTexts(editor)).toEqual([
      "This is the first paragraph of the document. It contains several sentences that should flow together as one continuous block of text when the page is reconstructed in the editor, rather than becoming one paragraph per line.",
      "This is the second paragraph. It starts after a clear vertical gap and has its own first line. It should remain separate from the paragraph above even though both paragraphs share the same left and right margins.",
      "First numbered item",
      "Second numbered item",
      "Third numbered item",
      "The left column contains a short paragraph that must not be merged with the right column even though the lines are close together vertically.",
      "The right column is a separate reading stream. Column-aware reconstruction keeps its lines together and in order.",
      "A final full-width paragraph closes the page. It should join the lines above into a single editable paragraph with normal wrapping.",
    ]);
  });

  it("accepts Justify on the reconstructed paragraphs", () => {
    editor = createEditor();
    insertReconstruction(editor);

    editor.commands.setTextSelection({
      from: 1,
      to: editor.state.doc.content.size - 1,
    });
    editor.chain().focus().setTextAlign("justify").run();

    const paragraphs = topLevelNodes(editor).filter(
      (node) => node.type === "paragraph",
    );
    expect(paragraphs.length).toBeGreaterThan(0);
    for (const paragraph of paragraphs) {
      expect(paragraph.attrs?.textAlign).toBe("justify");
    }
    // Justify must not have introduced a line break to fake the alignment.
    expect(JSON.stringify(editor.getJSON())).not.toContain("hardBreak");
  });

  it("keeps the structure and Justify after a save/reopen round-trip", () => {
    editor = createEditor();
    insertReconstruction(editor);
    editor.commands.setTextSelection({
      from: 1,
      to: editor.state.doc.content.size - 1,
    });
    editor.chain().focus().setTextAlign("justify").run();

    const saved = editor.getJSON();
    editor.destroy();

    const reopened = new Editor({
      extensions: createEditorExtensions(() => "Start writing"),
      content: saved,
    });
    editor = reopened;

    const nodes = topLevelNodes(reopened);
    expect(nodes.map((node) => node.type)).toEqual([
      "heading",
      "paragraph",
      "paragraph",
      "orderedList",
      "paragraph",
      "paragraph",
      "paragraph",
    ]);
    expect(
      nodes
        .filter((node) => node.type === "paragraph")
        .map((node) => node.attrs?.textAlign),
    ).toEqual(Array(5).fill("justify"));
    expect(JSON.stringify(saved)).not.toContain("hardBreak");
  });

  it("keeps a table block verbatim when the page is inserted", () => {
    editor = createEditor();
    editor
      .chain()
      .focus("end")
      .insertContent(
        ocrReconstructionContent(
          [
            {
              kind: "table",
              text: "Name  Value\nAlpha  1",
              x: 100,
              y: 100,
              width: 300,
              height: 60,
            },
          ],
          null,
        ),
      )
      .run();

    const nodes = topLevelNodes(editor);
    expect(nodes).toHaveLength(1);
    expect(nodes[0].type).toBe("paragraph");
    expect(nodeText(nodes[0])).toBe("Name  ValueAlpha  1");
    expect(JSON.stringify(nodes[0])).toContain("hardBreak");
  });
});
