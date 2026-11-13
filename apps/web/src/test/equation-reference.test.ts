import { Editor } from "@tiptap/core";
import type { JSONContent } from "@tiptap/core";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";

import { i18n, initI18n } from "@/i18n";
import {
  equationReferenceContent,
  equationReferenceLabel,
  numberedEquationTargets,
} from "@/lib/editor-equation-reference";
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

function equation(
  id: string | null,
  latex: string,
  numbered = true,
): JSONContent {
  return { type: "blockMath", attrs: { id, latex, numbered } };
}

function findReference(instance: Editor): JSONContent | undefined {
  const paragraph = instance
    .getJSON()
    .content?.find((node) => node.type === "paragraph");
  return paragraph?.content?.find((node) => node.type === "equationReference");
}

function seed(instance: Editor) {
  instance.commands.setContent({
    type: "doc",
    content: [
      equation("eq-a", "a = b"),
      {
        type: "paragraph",
        content: [
          { type: "text", text: "From " },
          equationReferenceContent("eq-b"),
          { type: "text", text: " and " },
          equationReferenceContent("eq-a"),
          { type: "text", text: "." },
        ],
      },
      equation("eq-b", "c = d"),
    ],
  });
}

describe("equation references", () => {
  it("lists numbered display equations in document order", () => {
    editor = createEditor();
    editor.commands.setContent({
      type: "doc",
      content: [
        equation("eq-a", "a = b"),
        equation("eq-b", "c = d", false),
        equation("eq-c", "e = f"),
        // A numbered equation without an id still consumes a number.
        equation(null, "g = h"),
        equation("eq-d", "i = j"),
      ],
    });

    expect(numberedEquationTargets(editor.state.doc)).toEqual([
      { id: "eq-a", number: 1, caption: "a = b", latex: "a = b" },
      { id: "eq-c", number: 2, caption: "e = f", latex: "e = f" },
      { id: "eq-d", number: 4, caption: "i = j", latex: "i = j" },
    ]);
  });

  it("never treats inline math as a numbered target", () => {
    editor = createEditor();
    editor.commands.setContent({
      type: "doc",
      content: [
        {
          type: "paragraph",
          content: [
            { type: "text", text: "Let " },
            { type: "inlineMath", attrs: { latex: "x^2" } },
            { type: "text", text: " be positive." },
          ],
        },
      ],
    });

    expect(numberedEquationTargets(editor.state.doc)).toEqual([]);
  });

  it("resolves a stored target id to the live number", () => {
    editor = createEditor();
    seed(editor);

    expect(equationReferenceLabel(editor.state, "eq-a")).toEqual({
      text: "Equation (1)",
      missing: false,
    });
    expect(equationReferenceLabel(editor.state, "eq-b")).toEqual({
      text: "Equation (2)",
      missing: false,
    });
  });

  it("renumbers a reference when the equations are reordered", () => {
    editor = createEditor();
    seed(editor);
    expect(equationReferenceLabel(editor.state, "eq-b").text).toBe("Equation (2)");

    // Same nodes, reversed order: the target id did not change, the label did.
    editor.commands.setContent({
      type: "doc",
      content: [equation("eq-b", "c = d"), equation("eq-a", "a = b")],
    });
    expect(equationReferenceLabel(editor.state, "eq-b").text).toBe("Equation (1)");
    expect(equationReferenceLabel(editor.state, "eq-a").text).toBe("Equation (2)");
  });

  it("marks a reference whose equation was deleted or unnumbered", () => {
    editor = createEditor();
    seed(editor);

    editor.commands.setContent({
      type: "doc",
      content: [equation("eq-b", "c = d", false)],
    });
    expect(equationReferenceLabel(editor.state, "eq-b")).toEqual({
      text: "Equation (missing)",
      missing: true,
    });
    expect(equationReferenceLabel(editor.state, "never-existed").missing).toBe(true);
  });

  it("renders the live label in the editor node view", () => {
    editor = createEditor();
    seed(editor);

    const references = editor.view.dom.querySelectorAll(".equation-reference");
    expect(references).toHaveLength(2);
    expect(references[0].textContent).toBe("Equation (2)");
    expect(references[0].getAttribute("data-missing")).toBe("false");
    expect(references[1].textContent).toBe("Equation (1)");
  });

  it("updates the rendered label after a language change", async () => {
    editor = createEditor();
    seed(editor);
    await i18n.changeLanguage("my");

    const reference = editor.view.dom.querySelector(".equation-reference");
    expect(reference?.textContent).toBe("ညီမျှခြင်း (2)");
  });

  it("stores only the target id and survives an HTML round-trip", () => {
    editor = createEditor();
    seed(editor);

    const reference = findReference(editor);
    expect(reference?.attrs).toEqual({ targetId: "eq-b" });

    const html = editor.getHTML();
    expect(html).toContain('data-equation-reference="eq-b"');

    editor.commands.setContent(html);
    const restored = findReference(editor);
    expect(restored?.attrs).toEqual({ targetId: "eq-b" });
  });
});
