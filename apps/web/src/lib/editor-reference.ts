import { Node, mergeAttributes } from "@tiptap/core";
import type { Node as PMNode } from "@tiptap/pm/model";
import type { EditorState } from "@tiptap/pm/state";

import { i18n } from "@/i18n";

/** A numbered figure that can be referenced from prose. */
export interface FigureTarget {
  id: string;
  number: number;
  caption: string;
}

export interface FigureReferenceLabel {
  text: string;
  missing: boolean;
}

function translate(key: string, fallback: string, options?: Record<string, unknown>): string {
  if (!i18n.isInitialized) {
    return fallback.replace(/\{\{(\w+)\}\}/g, (match, name: string) =>
      options && name in options ? String(options[name]) : match,
    );
  }
  const value = i18n.t(key, { ns: "workspace", defaultValue: fallback, ...options });
  return typeof value === "string" && value ? value : fallback;
}

/**
 * Read numbered figures in document order. A numbered figure without an id still
 * consumes a number, so a reference can never point at the wrong one.
 */
export function numberedFigureTargets(doc: PMNode): FigureTarget[] {
  const targets: FigureTarget[] = [];
  let number = 0;
  doc.descendants((node) => {
    if (node.type.name !== "figure" || !node.attrs.numbered) return true;
    number += 1;
    const id = typeof node.attrs.id === "string" ? node.attrs.id.trim() : "";
    if (id) {
      targets.push({ id, number, caption: String(node.attrs.caption ?? "") });
    }
    return true;
  });
  return targets;
}

/** Resolve the visible label for a reference, or a clear missing-target marker. */
export function figureReferenceLabel(
  state: EditorState,
  targetId: string,
): FigureReferenceLabel {
  const target = numberedFigureTargets(state.doc).find((item) => item.id === targetId);
  if (!target) {
    return {
      text: translate("editor.figure.referenceMissing", "Figure (missing)"),
      missing: true,
    };
  }
  return {
    text: translate("editor.figure.referenceLabel", "Figure {{n}}", { n: target.number }),
    missing: false,
  };
}

/**
 * An inline atom that points at a numbered figure by its stable id. The number is
 * never stored; it is resolved from the document so it follows the figure when it
 * moves or is renumbered. A deleted target stays as an explicit missing marker
 * instead of silently becoming a different number.
 */
export const FigureReference = Node.create({
  name: "figureReference",
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      targetId: {
        default: "",
        parseHTML: (element) => element.getAttribute("data-figure-reference") ?? "",
        renderHTML: (attributes) =>
          attributes.targetId
            ? { "data-figure-reference": String(attributes.targetId) }
            : {},
      },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-figure-reference]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(HTMLAttributes, { class: "figure-reference" }),
    ];
  },

  addNodeView() {
    return ({ node, editor }) => {
      const dom = document.createElement("span");
      dom.className = "figure-reference";
      dom.contentEditable = "false";
      let current = node;

      const render = () => {
        const label = figureReferenceLabel(editor.state, String(current.attrs.targetId ?? ""));
        dom.textContent = label.text;
        dom.dataset.missing = label.missing ? "true" : "false";
      };

      render();
      const onTransaction = () => render();
      const onLanguageChange = () => render();
      editor.on("transaction", onTransaction);
      i18n.on("languageChanged", onLanguageChange);

      return {
        dom,
        update(updated) {
          if (updated.type.name !== "figureReference") return false;
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

/** Insert an inline reference to a numbered figure. */
export function figureReferenceContent(targetId: string) {
  return { type: "figureReference", attrs: { targetId } };
}
