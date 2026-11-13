import { Node, mergeAttributes } from "@tiptap/core";
import type { JSONContent } from "@tiptap/core";
import type { Node as PMNode } from "@tiptap/pm/model";
import { NodeSelection } from "@tiptap/pm/state";
import type { EditorState } from "@tiptap/pm/state";

import { i18n } from "@/i18n";
import { translateWorkspace } from "./editor-i18n";

/** A footnote selected in the editor. The number is derived, never stored. */
export interface SelectedFootnote {
  pos: number;
  id: string | null;
  text: string;
  number: number | null;
}

function readFootnote(node: PMNode, pos: number, number: number | null): SelectedFootnote {
  return {
    pos,
    id:
      typeof node.attrs.id === "string" && node.attrs.id.trim()
        ? node.attrs.id
        : null,
    text: String(node.attrs.text ?? ""),
    number,
  };
}

/** A stable id for a footnote, so it survives edits and saves. */
export function createFootnoteId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `footnote-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/** Stored document content for one footnote. */
export function footnoteContent(text: string, id: string | null = null): JSONContent {
  return { type: "footnote", attrs: { text, id: id ?? createFootnoteId() } };
}

/** Map each footnote position to its document-order number. */
function footnoteNumbers(doc: PMNode): Map<number, number> {
  const numbers = new Map<number, number>();
  let number = 0;
  doc.descendants((node, pos) => {
    if (node.type.name === "footnote") {
      number += 1;
      numbers.set(pos, number);
    }
    return true;
  });
  return numbers;
}

/** The document-order number of the footnote at `pos`, or null. */
export function footnoteNumberAt(doc: PMNode, pos: number): number | null {
  return footnoteNumbers(doc).get(pos) ?? null;
}

/** Read the footnote at an exact document position. */
export function footnoteAt(state: EditorState, pos: number): SelectedFootnote | null {
  const node = state.doc.nodeAt(pos);
  if (!node || node.type.name !== "footnote") return null;
  return readFootnote(node, pos, footnoteNumberAt(state.doc, pos));
}

/** A footnote is editable only when the whole atom is selected. */
export function selectedFootnote(state: EditorState): SelectedFootnote | null {
  const selection = state.selection;
  if (!(selection instanceof NodeSelection)) return null;
  if (selection.node.type.name !== "footnote") return null;
  return readFootnote(
    selection.node,
    selection.from,
    footnoteNumberAt(state.doc, selection.from),
  );
}

/**
 * Footnote texts in document order. Every atom keeps its slot, even when its text
 * is empty, so the index matches the generated number and the exported definition.
 */
export function footnoteTexts(doc: PMNode): string[] {
  const texts: string[] = [];
  doc.descendants((node) => {
    if (node.type.name === "footnote") {
      texts.push(String(node.attrs.text ?? "").trim());
    }
    return true;
  });
  return texts;
}

/**
 * A readable notes section for the stored plain text. Footnote text lives on the
 * atom, so `editor.getText()` cannot see it; adding it here keeps the version
 * preview and diff aware of footnote edits.
 */
export function footnoteNotesText(doc: PMNode): string {
  const notes = footnoteTexts(doc);
  // A document whose notes are all empty has nothing readable to add.
  if (!notes.some(Boolean)) return "";
  return `Notes:\n${notes.map((note, index) => `[${index + 1}] ${note}`).join("\n")}`;
}

/**
 * An inline atom that stores its own note text. The visible number is generated
 * from document order, so inserting or deleting a footnote renumbers the rest
 * without rewriting stored text. The number is never saved.
 */
export const FootnoteNode = Node.create({
  name: "footnote",
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      text: {
        default: "",
        parseHTML: (element) => element.getAttribute("data-footnote-text") ?? "",
        renderHTML: (attributes) =>
          attributes.text
            ? { "data-footnote-text": String(attributes.text) }
            : {},
      },
      id: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-footnote-id"),
        renderHTML: (attributes) =>
          attributes.id ? { "data-footnote-id": String(attributes.id) } : {},
      },
    };
  },

  parseHTML() {
    // Accept an atom whose id is missing but whose text survived, so a legacy or
    // hand-built document is not silently dropped on an HTML round-trip.
    return [{ tag: "sup[data-footnote-id]" }, { tag: "sup[data-footnote-text]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "sup",
      mergeAttributes(HTMLAttributes, { class: "doc-footnote" }),
    ];
  },

  addNodeView() {
    return ({ node, editor, getPos }) => {
      const dom = document.createElement("sup");
      dom.className = "doc-footnote";
      dom.contentEditable = "false";
      let current = node;

      const render = () => {
        const position = typeof getPos === "function" ? getPos() : null;
        const number =
          typeof position === "number"
            ? footnoteNumberAt(editor.state.doc, position)
            : null;
        dom.textContent = number ? String(number) : "";
        dom.dataset.number = number ? String(number) : "";
        dom.setAttribute(
          "aria-label",
          number
            ? translateWorkspace("editor.footnote.ariaLabel", "Footnote {{n}}", {
                n: number,
              })
            : translateWorkspace("editor.footnote.label", "Footnote"),
        );
        dom.title = String(current.attrs.text ?? "");
      };

      render();
      const onTransaction = () => render();
      const onLanguageChange = () => render();
      editor.on("transaction", onTransaction);
      i18n.on("languageChanged", onLanguageChange);

      return {
        dom,
        update(updated) {
          if (updated.type.name !== "footnote") return false;
          current = updated;
          render();
          return true;
        },
        destroy() {
          editor.off("transaction", onTransaction);
          i18n.off("languageChanged", onLanguageChange);
        },
      };
    };
  },
});
