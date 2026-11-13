import { Editor } from "@tiptap/core";
import type { JSONContent } from "@tiptap/core";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";

import { i18n, initI18n } from "@/i18n";
import {
  createFootnoteId,
  footnoteAt,
  footnoteContent,
  footnoteNotesText,
  footnoteNumberAt,
  footnoteTexts,
  selectedFootnote,
} from "@/lib/editor-footnote";
import { createEditorExtensions } from "@/lib/editor-extensions";

let editor: Editor | null = null;

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

beforeEach(async () => {
  await i18n.changeLanguage("en");
});

afterEach(() => {
  editor?.destroy();
  editor = null;
});

function createEditor(): Editor {
  return new Editor({
    extensions: createEditorExtensions(() => ""),
    content: { type: "doc", content: [{ type: "paragraph" }] },
  });
}

function seed(instance: Editor) {
  instance.commands.setContent({
    type: "doc",
    content: [
      {
        type: "paragraph",
        content: [
          { type: "text", text: "First" },
          footnoteContent("First note.", "fn-a"),
          { type: "text", text: " second" },
          footnoteContent("Second note.", "fn-b"),
          { type: "text", text: "." },
        ],
      },
    ],
  });
}

function footnotePositions(instance: Editor): number[] {
  const positions: number[] = [];
  instance.state.doc.descendants((node, pos) => {
    if (node.type.name === "footnote") positions.push(pos);
    return true;
  });
  return positions;
}

function findFootnotes(instance: Editor): JSONContent[] {
  const paragraph = instance
    .getJSON()
    .content?.find((node) => node.type === "paragraph");
  return (paragraph?.content ?? []).filter((node) => node.type === "footnote");
}

describe("footnotes", () => {
  it("stores the note text and a stable id, never a number", () => {
    editor = createEditor();
    seed(editor);

    const notes = findFootnotes(editor);
    expect(notes).toHaveLength(2);
    expect(notes[0].attrs).toEqual({ text: "First note.", id: "fn-a" });
    expect(notes[1].attrs).toEqual({ text: "Second note.", id: "fn-b" });

    const html = editor.getHTML();
    expect(html).toContain('data-footnote-id="fn-a"');
    expect(html).toContain('data-footnote-text="First note."');

    editor.commands.setContent(html);
    expect(findFootnotes(editor)[0].attrs).toEqual({
      text: "First note.",
      id: "fn-a",
    });
  });

  it("round-trips a footnote that has text but no id", () => {
    editor = createEditor();
    editor.commands.setContent(
      '<p>A<sup data-footnote-text="Note without id"></sup>.</p>',
    );

    const note = findFootnotes(editor)[0];
    expect(note.attrs).toEqual({ text: "Note without id", id: null });
    expect(footnoteNumberAt(editor.state.doc, footnotePositions(editor)[0])).toBe(1);
  });

  it("generates a distinct id when none is supplied", () => {
    const first = footnoteContent("Note");
    const second = footnoteContent("Note");
    expect(typeof first.attrs?.id).toBe("string");
    expect(first.attrs?.id).not.toBe(second.attrs?.id);
    expect(createFootnoteId()).not.toBe(createFootnoteId());
  });

  it("is editable only when the whole atom is selected", () => {
    editor = createEditor();
    seed(editor);
    const [pos] = footnotePositions(editor);

    editor.commands.setTextSelection(1);
    expect(selectedFootnote(editor.state)).toBeNull();

    editor.commands.setNodeSelection(pos);
    expect(selectedFootnote(editor.state)).toEqual({
      pos,
      id: "fn-a",
      text: "First note.",
      number: 1,
    });
    expect(footnoteAt(editor.state, pos)).toEqual(selectedFootnote(editor.state));
    expect(footnoteAt(editor.state, pos + 1)).toBeNull();
  });

  it("numbers notes in document order and renumbers after a deletion", () => {
    editor = createEditor();
    seed(editor);
    const [first, second] = footnotePositions(editor);

    expect(footnoteNumberAt(editor.state.doc, first)).toBe(1);
    expect(footnoteNumberAt(editor.state.doc, second)).toBe(2);
    const markers = editor.view.dom.querySelectorAll(".doc-footnote");
    expect(Array.from(markers).map((marker) => marker.textContent)).toEqual([
      "1",
      "2",
    ]);

    const node = editor.state.doc.nodeAt(first);
    expect(node).not.toBeNull();
    editor
      .chain()
      .command(({ tr }) => {
        tr.delete(first, first + (node?.nodeSize ?? 0));
        return true;
      })
      .run();

    const [remaining] = footnotePositions(editor);
    expect(footnoteNumberAt(editor.state.doc, remaining)).toBe(1);
    expect(
      editor.view.dom.querySelector(".doc-footnote")?.textContent,
    ).toBe("1");
  });

  it("renumbers after inserting a note before an existing one", () => {
    editor = createEditor();
    seed(editor);
    const [first] = footnotePositions(editor);

    editor.commands.insertContentAt(first, footnoteContent("New note.", "fn-new"));

    const positions = footnotePositions(editor);
    expect(positions).toHaveLength(3);
    expect(footnoteAt(editor.state, positions[0])?.text).toBe("New note.");
    expect(footnoteNumberAt(editor.state.doc, positions[0])).toBe(1);
    expect(footnoteNumberAt(editor.state.doc, positions[1])).toBe(2);
    expect(footnoteNumberAt(editor.state.doc, positions[2])).toBe(3);
  });

  it("renders a localized accessible label and the note text as a title", async () => {
    editor = createEditor();
    seed(editor);

    const first = editor.view.dom.querySelector(".doc-footnote") as HTMLElement;
    expect(first.getAttribute("aria-label")).toBe("Footnote 1");
    expect(first.getAttribute("title")).toBe("First note.");

    await i18n.changeLanguage("my");
    expect(first.getAttribute("aria-label")).toBe("အောက်ခြေမှတ်စု 1");
  });

  it("reads note text for the stored plain-text preview", () => {
    editor = createEditor();
    expect(footnoteTexts(editor.state.doc)).toEqual([]);
    expect(footnoteNotesText(editor.state.doc)).toBe("");

    seed(editor);
    expect(footnoteTexts(editor.state.doc)).toEqual([
      "First note.",
      "Second note.",
    ]);
    expect(footnoteNotesText(editor.state.doc)).toBe(
      "Notes:\n[1] First note.\n[2] Second note.",
    );
  });

  it("keeps an empty note's slot in the preview numbering", () => {
    editor = createEditor();
    editor.commands.setContent({
      type: "doc",
      content: [
        {
          type: "paragraph",
          content: [
            { type: "text", text: "A" },
            footnoteContent("", "fn-empty"),
            { type: "text", text: "B" },
            footnoteContent("Real note.", "fn-real"),
          ],
        },
      ],
    });

    expect(footnoteTexts(editor.state.doc)).toEqual(["", "Real note."]);
    expect(footnoteNotesText(editor.state.doc)).toBe(
      "Notes:\n[1] \n[2] Real note.",
    );
    // The atom still occupies a position, so the real note stays number 2.
    const [, real] = footnotePositions(editor);
    expect(footnoteNumberAt(editor.state.doc, real)).toBe(2);
    expect(
      Array.from(editor.view.dom.querySelectorAll(".doc-footnote")).map(
        (marker) => marker.textContent,
      ),
    ).toEqual(["1", "2"]);
  });
});
