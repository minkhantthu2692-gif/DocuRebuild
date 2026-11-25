import { Editor } from "@tiptap/core";
import { afterEach, describe, expect, it } from "vitest";

import { createEditorExtensions } from "@/lib/editor-extensions";
import {
  collectFontFamilies,
  cssFontFamily,
  sanitizeFontFamily,
} from "@/lib/fonts";

let editor: Editor | null = null;

afterEach(() => {
  editor?.destroy();
  editor = null;
});

function createEditor(content?: Record<string, unknown>): Editor {
  return new Editor({
    extensions: createEditorExtensions(() => "Start writing"),
    content: content ?? {
      type: "doc",
      content: [{ type: "paragraph", content: [{ type: "text", text: "AB" }] }],
    },
  });
}

function selectAll(instance: Editor): void {
  instance.commands.setTextSelection({ from: 1, to: instance.state.doc.content.size - 1 });
}

describe("scientific notation marks", () => {
  it("applies and removes superscript through the Tiptap command", () => {
    editor = createEditor();
    selectAll(editor);

    editor.chain().focus().toggleSuperscript().run();

    const text = editor.getJSON().content?.[0]?.content?.[0];
    expect(text?.marks).toEqual([{ type: "superscript" }]);
    expect(editor.getHTML()).toContain("<sup>AB</sup>");
    expect(editor.isActive("superscript")).toBe(true);

    editor.chain().focus().toggleSuperscript().run();
    expect(editor.getJSON().content?.[0]?.content?.[0]?.marks).toBeUndefined();
  });

  it("applies and removes subscript through the Tiptap command", () => {
    editor = createEditor();
    selectAll(editor);

    editor.chain().focus().toggleSubscript().run();

    expect(editor.getJSON().content?.[0]?.content?.[0]?.marks).toEqual([
      { type: "subscript" },
    ]);
    expect(editor.getHTML()).toContain("<sub>AB</sub>");
  });

  it("keeps the format after a save and reload of the document JSON", () => {
    editor = createEditor({
      type: "doc",
      content: [
        {
          type: "paragraph",
          content: [
            { type: "text", text: "E = mc" },
            {
              type: "text",
              text: "2",
              marks: [{ type: "superscript" }],
            },
          ],
        },
      ],
    });

    const saved = editor.getJSON();
    editor.destroy();

    editor = createEditor(saved as unknown as Record<string, unknown>);
    expect(editor.getHTML()).toContain("E = mc<sup>2</sup>");
  });
});

describe("font family mark", () => {
  it("stores the family in a textStyle mark and renders it inline", () => {
    editor = createEditor();
    selectAll(editor);

    editor.chain().focus().setFontFamily("Docu Serif").run();

    const text = editor.getJSON().content?.[0]?.content?.[0];
    expect(text?.marks).toEqual([
      { type: "textStyle", attrs: { fontFamily: "Docu Serif" } },
    ]);
    expect(editor.getHTML()).toContain('style="font-family: Docu Serif;"');
    expect(editor.getAttributes("textStyle").fontFamily).toBe("Docu Serif");

    editor.chain().focus().unsetFontFamily().run();
    expect(editor.getJSON().content?.[0]?.content?.[0]?.marks).toBeUndefined();
  });

  it("round-trips the family with a superscript mark on the same text", () => {
    editor = createEditor();
    selectAll(editor);

    editor
      .chain()
      .focus()
      .setFontFamily("Docu Serif")
      .toggleSuperscript()
      .run();

    const saved = editor.getJSON();
    editor.destroy();
    editor = createEditor(saved as unknown as Record<string, unknown>);

    expect(editor.getAttributes("textStyle").fontFamily).toBe("Docu Serif");
    expect(editor.getJSON().content?.[0]?.content?.[0]?.marks).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ type: "textStyle" }),
        expect.objectContaining({ type: "superscript" }),
      ]),
    );
  });
});

describe("font helpers", () => {
  it("sanitizes names that could break CSS or markup", () => {
    expect(sanitizeFontFamily('  "Docu Serif"  ')).toBe("Docu Serif");
    expect(sanitizeFontFamily('Bad"; background:url(x); "')).toBe(
      "Bad background:url(x)",
    );
    expect(sanitizeFontFamily(undefined)).toBe("");
    expect(cssFontFamily("Docu Serif")).toBe('"Docu Serif"');
  });

  it("collects families from nested document marks without duplicates", () => {
    const content = {
      type: "doc",
      content: [
        {
          type: "paragraph",
          content: [
            {
              type: "text",
              text: "one",
              marks: [
                { type: "textStyle", attrs: { fontFamily: "Docu Serif" } },
                { type: "superscript" },
              ],
            },
            {
              type: "text",
              text: "two",
              marks: [
                { type: "textStyle", attrs: { fontFamily: "docu serif" } },
              ],
            },
          ],
        },
        {
          type: "bulletList",
          content: [
            {
              type: "listItem",
              content: [
                {
                  type: "paragraph",
                  content: [
                    {
                      type: "text",
                      text: "three",
                      marks: [
                        {
                          type: "textStyle",
                          attrs: { fontFamily: "Docu Sans" },
                        },
                      ],
                    },
                  ],
                },
              ],
            },
          ],
        },
      ],
    };

    expect(collectFontFamilies(content).sort()).toEqual([
      "Docu Sans",
      "Docu Serif",
    ]);
    expect(collectFontFamilies(null)).toEqual([]);
  });
});

describe("editor extension registration", () => {
  it("registers the typography extensions and their shortcuts", () => {
    editor = createEditor();
    const names = new Set(editor.extensionManager.extensions.map((entry) => entry.name));

    expect(names.has("textStyle")).toBe(true);
    expect(names.has("fontFamily")).toBe(true);
    expect(names.has("superscript")).toBe(true);
    expect(names.has("subscript")).toBe(true);

    const superscript = editor.extensionManager.extensions.find(
      (entry) => entry.name === "superscript",
    );
    const subscript = editor.extensionManager.extensions.find(
      (entry) => entry.name === "subscript",
    );
    const shortcutKeys = (extension: typeof superscript) => {
      const factory = extension?.config.addKeyboardShortcuts as
        | ((this: unknown) => Record<string, unknown>)
        | undefined;
      return Object.keys(factory?.call(extension) ?? {});
    };

    const superscriptKeys = shortcutKeys(superscript);
    const subscriptKeys = shortcutKeys(subscript);

    expect(superscriptKeys).toContain("Mod-.");
    expect(subscriptKeys).toContain("Mod-,");
  });
});

describe("text alignment", () => {
  it("applies justify alignment through the Tiptap command", () => {
    editor = createEditor();
    selectAll(editor);

    editor.chain().focus().setTextAlign("justify").run();

    expect(editor.getJSON().content?.[0]?.attrs).toMatchObject({
      textAlign: "justify",
    });
    expect(editor.isActive({ textAlign: "justify" })).toBe(true);

    editor.chain().focus().unsetTextAlign().run();
    expect(editor.getJSON().content?.[0]?.attrs?.textAlign).toBeNull();
  });

  it("applies left, center, and right alignments", () => {
    for (const align of ["left", "center", "right"] as const) {
      editor = createEditor();
      selectAll(editor);
      editor.chain().focus().setTextAlign(align).run();
      expect(editor.getJSON().content?.[0]?.attrs).toMatchObject({
        textAlign: align,
      });
      editor.destroy();
      editor = null;
    }
  });

  it("preserves justify alignment after a save and reload", () => {
    editor = createEditor({
      type: "doc",
      content: [
        {
          type: "paragraph",
          attrs: { textAlign: "justify" },
          content: [{ type: "text", text: "Justified text." }],
        },
      ],
    });

    const saved = editor.getJSON();
    editor.destroy();
    editor = createEditor(saved as unknown as Record<string, unknown>);

    expect(editor.getJSON().content?.[0]?.attrs).toMatchObject({
      textAlign: "justify",
    });
  });
});
