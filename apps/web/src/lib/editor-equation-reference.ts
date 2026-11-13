import type { Node as PMNode } from "@tiptap/pm/model";
import type { EditorState } from "@tiptap/pm/state";

import {
  createReferenceNode,
  resolveReferenceLabel,
  type ReferenceLabel,
  type ReferenceTarget,
} from "./editor-reference";

/** A numbered display equation that can be referenced from prose. */
export interface EquationTarget extends ReferenceTarget {
  latex: string;
}

/**
 * Read numbered display equations in document order. A numbered equation without
 * an id still consumes a number, so a reference can never point at the wrong one.
 * Inline math is never numbered and is not a target.
 */
export function numberedEquationTargets(doc: PMNode): EquationTarget[] {
  const targets: EquationTarget[] = [];
  let number = 0;
  doc.descendants((node) => {
    if (node.type.name !== "blockMath" || !node.attrs.numbered) return true;
    number += 1;
    const id = typeof node.attrs.id === "string" ? node.attrs.id.trim() : "";
    if (id) {
      const latex = String(node.attrs.latex ?? "");
      targets.push({ id, number, caption: latex, latex });
    }
    return true;
  });
  return targets;
}

/** Resolve the visible label for an equation reference. */
export function equationReferenceLabel(
  state: EditorState,
  targetId: string,
): ReferenceLabel {
  return resolveReferenceLabel(
    targetId,
    numberedEquationTargets(state.doc),
    {
      label: "editor.equation.referenceLabel",
      missing: "editor.equation.referenceMissing",
    },
    { label: "Equation ({{n}})", missing: "Equation (missing)" },
  );
}

export const EquationReference = createReferenceNode({
  name: "equationReference",
  dataAttribute: "data-equation-reference",
  className: "equation-reference",
  label: equationReferenceLabel,
});

/** Insert an inline reference to a numbered display equation. */
export function equationReferenceContent(targetId: string) {
  return { type: "equationReference", attrs: { targetId } };
}
