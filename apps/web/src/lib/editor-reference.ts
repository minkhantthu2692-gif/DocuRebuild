import { Node, mergeAttributes } from "@tiptap/core";
import type { Node as PMNode } from "@tiptap/pm/model";
import type { EditorState } from "@tiptap/pm/state";

import { i18n } from "@/i18n";
import { translateWorkspace } from "./editor-i18n";

/** A numbered node that can be referenced from prose. */
export interface ReferenceTarget {
  id: string;
  number: number;
  caption: string;
}

export interface ReferenceLabel {
  text: string;
  missing: boolean;
}

export type FigureTarget = ReferenceTarget;
export type FigureReferenceLabel = ReferenceLabel;

/** Resolve a target id to its visible label, or an explicit missing marker. */
export function resolveReferenceLabel(
  targetId: string,
  targets: ReferenceTarget[],
  keys: { label: string; missing: string },
  fallbacks: { label: string; missing: string },
): ReferenceLabel {
  const target = targets.find((item) => item.id === targetId);
  if (!target) {
    return { text: translateWorkspace(keys.missing, fallbacks.missing), missing: true };
  }
  return {
    text: translateWorkspace(keys.label, fallbacks.label, { n: target.number }),
    missing: false,
  };
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

/** Resolve the visible label for a figure reference. */
export function figureReferenceLabel(
  state: EditorState,
  targetId: string,
): FigureReferenceLabel {
  return resolveReferenceLabel(
    targetId,
    numberedFigureTargets(state.doc),
    {
      label: "editor.figure.referenceLabel",
      missing: "editor.figure.referenceMissing",
    },
    { label: "Figure {{n}}", missing: "Figure (missing)" },
  );
}

interface ReferenceNodeOptions {
  name: string;
  dataAttribute: string;
  className: string;
  label: (state: EditorState, targetId: string) => ReferenceLabel;
}

/**
 * An inline atom that points at a numbered node by its stable id. The number is
 * never stored; it is resolved from the document so it follows the target when it
 * moves or is renumbered. A deleted target stays as an explicit missing marker
 * instead of silently becoming a different number.
 *
 * Figures and equations share this implementation so their behaviour cannot drift.
 */
export function createReferenceNode({
  name,
  dataAttribute,
  className,
  label,
}: ReferenceNodeOptions) {
  return Node.create({
    name,
    group: "inline",
    inline: true,
    atom: true,
    selectable: true,

    addAttributes() {
      return {
        targetId: {
          default: "",
          parseHTML: (element) => element.getAttribute(dataAttribute) ?? "",
          renderHTML: (attributes) =>
            attributes.targetId
              ? { [dataAttribute]: String(attributes.targetId) }
              : {},
        },
      };
    },

    parseHTML() {
      return [{ tag: `span[${dataAttribute}]` }];
    },

    renderHTML({ HTMLAttributes }) {
      return [
        "span",
        mergeAttributes(HTMLAttributes, { class: className }),
      ];
    },

    addNodeView() {
      return ({ node, editor }) => {
        const dom = document.createElement("span");
        dom.className = className;
        dom.contentEditable = "false";
        let current = node;

        const render = () => {
          const resolved = label(editor.state, String(current.attrs.targetId ?? ""));
          dom.textContent = resolved.text;
          dom.dataset.missing = resolved.missing ? "true" : "false";
        };

        render();
        const onTransaction = () => render();
        const onLanguageChange = () => render();
        editor.on("transaction", onTransaction);
        i18n.on("languageChanged", onLanguageChange);

        return {
          dom,
          update(updated) {
            if (updated.type.name !== name) return false;
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
}

export const FigureReference = createReferenceNode({
  name: "figureReference",
  dataAttribute: "data-figure-reference",
  className: "figure-reference",
  label: figureReferenceLabel,
});

/** Insert an inline reference to a numbered figure. */
export function figureReferenceContent(targetId: string) {
  return { type: "figureReference", attrs: { targetId } };
}
