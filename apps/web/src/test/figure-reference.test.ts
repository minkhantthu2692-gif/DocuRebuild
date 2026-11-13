import { Editor } from "@tiptap/core";
import type { JSONContent } from "@tiptap/core";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";

import { i18n, initI18n } from "@/i18n";
import { createEditorExtensions } from "@/lib/editor-extensions";
import {
  figureReferenceContent,
  figureReferenceLabel,
  numberedFigureTargets,
} from "@/lib/editor-reference";

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

function figure(id: string | null, caption: string, numbered = true): JSONContent {
  return {
    type: "figure",
    attrs: {
      id,
      src: `/api/projects/p/assets/${id ?? "none"}/file`,
      alt: caption,
      caption,
      note: null,
      width: null,
      height: null,
      numbered,
    },
  };
}

function findReference(instance: Editor): JSONContent | undefined {
  const paragraph = instance
    .getJSON()
    .content?.find((node) => node.type === "paragraph");
  return paragraph?.content?.find((node) => node.type === "figureReference");
}

function seed(instance: Editor) {
  instance.commands.setContent({
    type: "doc",
    content: [
      figure("fig-a", "First"),
      {
        type: "paragraph",
        content: [
          { type: "text", text: "See " },
          figureReferenceContent("fig-b"),
          { type: "text", text: " and " },
          figureReferenceContent("fig-a"),
          { type: "text", text: "." },
        ],
      },
      figure("fig-b", "Second"),
    ],
  });
}

describe("figure references", () => {
  it("lists numbered figures in document order", () => {
    editor = createEditor();
    editor.commands.setContent({
      type: "doc",
      content: [
        figure("fig-a", "First"),
        figure("fig-b", "Unnumbered", false),
        figure("fig-c", "Third"),
        // A numbered figure without an id still consumes a number.
        figure(null, "No id"),
        figure("fig-d", "Fifth"),
      ],
    });

    expect(numberedFigureTargets(editor.state.doc)).toEqual([
      { id: "fig-a", number: 1, caption: "First" },
      { id: "fig-c", number: 2, caption: "Third" },
      { id: "fig-d", number: 4, caption: "Fifth" },
    ]);
  });

  it("resolves a stored target id to the live number", () => {
    editor = createEditor();
    seed(editor);

    expect(figureReferenceLabel(editor.state, "fig-a")).toEqual({
      text: "Figure 1",
      missing: false,
    });
    expect(figureReferenceLabel(editor.state, "fig-b")).toEqual({
      text: "Figure 2",
      missing: false,
    });
  });

  it("renumbers a reference when the figures are reordered", () => {
    editor = createEditor();
    seed(editor);
    expect(figureReferenceLabel(editor.state, "fig-b").text).toBe("Figure 2");

    // Same nodes, reversed order: the target id did not change, the label did.
    editor.commands.setContent({
      type: "doc",
      content: [figure("fig-b", "Second"), figure("fig-a", "First")],
    });
    expect(figureReferenceLabel(editor.state, "fig-b").text).toBe("Figure 1");
    expect(figureReferenceLabel(editor.state, "fig-a").text).toBe("Figure 2");
  });

  it("marks a reference whose figure was deleted or unnumbered", () => {
    editor = createEditor();
    seed(editor);

    editor.commands.setContent({
      type: "doc",
      content: [figure("fig-b", "Second", false)],
    });
    expect(figureReferenceLabel(editor.state, "fig-b")).toEqual({
      text: "Figure (missing)",
      missing: true,
    });
    expect(figureReferenceLabel(editor.state, "never-existed").missing).toBe(true);
  });

  it("renders the live label in the editor node view", () => {
    editor = createEditor();
    seed(editor);

    const references = editor.view.dom.querySelectorAll(".figure-reference");
    expect(references).toHaveLength(2);
    expect(references[0].textContent).toBe("Figure 2");
    expect(references[0].getAttribute("data-missing")).toBe("false");
    expect(references[1].textContent).toBe("Figure 1");
  });

  it("updates the rendered label after a language change", async () => {
    editor = createEditor();
    seed(editor);
    await i18n.changeLanguage("my");

    const reference = editor.view.dom.querySelector(".figure-reference");
    expect(reference?.textContent).toBe("ပုံ 2");
  });

  it("stores only the target id and survives an HTML round-trip", () => {
    editor = createEditor();
    seed(editor);

    const reference = findReference(editor);
    expect(reference?.attrs).toEqual({ targetId: "fig-b" });

    const html = editor.getHTML();
    expect(html).toContain('data-figure-reference="fig-b"');

    editor.commands.setContent(html);
    const restored = findReference(editor);
    expect(restored?.attrs).toEqual({ targetId: "fig-b" });
  });
});
