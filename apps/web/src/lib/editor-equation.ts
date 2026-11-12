import type { Node as PMNode } from "@tiptap/pm/model";
import { NodeSelection } from "@tiptap/pm/state";
import type { EditorState } from "@tiptap/pm/state";
import katex from "katex";

import type { JSONContent } from "@tiptap/core";

export interface EquationPreview {
  /** Rendered KaTeX markup, or null when the source is blank or invalid. */
  html: string | null;
  /** True when KaTeX rejected the source, so it must not be saved. */
  error: boolean;
}

/**
 * A block equation selected in the editor. LaTeX is stored as plain text on the
 * node; nothing is rendered into the saved document.
 */
export interface SelectedEquation {
  pos: number;
  latex: string;
}

function readEquation(node: PMNode, pos: number): SelectedEquation {
  return { pos, latex: String(node.attrs.latex ?? "") };
}

/** Read the selected block equation, if the selection is exactly one. */
export function selectedEquation(state: EditorState): SelectedEquation | null {
  const { selection } = state;
  if (!(selection instanceof NodeSelection) || selection.node.type.name !== "blockMath") {
    return null;
  }
  return readEquation(selection.node, selection.from);
}

/**
 * Read the block equation stored at a position. Returns null when the document
 * changed since the position was captured, so a dialog cannot edit another node.
 */
export function equationAt(state: EditorState, pos: number): SelectedEquation | null {
  // `nodeAt` throws for positions outside the document, so bound it first.
  if (!Number.isInteger(pos) || pos < 0 || pos >= state.doc.content.size) return null;
  const node = state.doc.nodeAt(pos);
  if (!node || node.type.name !== "blockMath") return null;
  return readEquation(node, pos);
}

/** Stored document content for one block equation. */
export function equationContent(latex: string): JSONContent {
  return { type: "blockMath", attrs: { latex } };
}

/**
 * Render display LaTeX locally for the dialog preview. Invalid source is
 * reported instead of inserted, so a broken equation is never saved silently.
 * KaTeX runs with `trust: false`, so the returned markup cannot contain
 * arbitrary links or HTML from the LaTeX source.
 */
export function renderEquationPreview(latex: string): EquationPreview {
  const source = latex.trim();
  if (!source) return { html: null, error: false };
  try {
    return {
      html: katex.renderToString(source, {
        displayMode: true,
        throwOnError: true,
        strict: "ignore",
        trust: false,
      }),
      error: false,
    };
  } catch {
    return { html: null, error: true };
  }
}
