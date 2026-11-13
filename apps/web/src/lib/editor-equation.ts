import type {
  JSONContent,
  NodeViewRenderer,
  NodeViewRendererProps,
} from "@tiptap/core";
import { BlockMath } from "@tiptap/extension-mathematics";
import type { Node as PMNode } from "@tiptap/pm/model";
import { NodeSelection } from "@tiptap/pm/state";
import type { EditorState } from "@tiptap/pm/state";
import katex from "katex";

export type EquationKind = "block" | "inline";

export interface EquationPreview {
  /** Rendered KaTeX markup, or null when the source is blank or invalid. */
  html: string | null;
  /** True when KaTeX rejected the source, so it must not be saved. */
  error: boolean;
}

/**
 * An equation selected in the editor. LaTeX is stored as plain text on the
 * node; nothing is rendered into the saved document.
 */
export interface SelectedEquation {
  pos: number;
  latex: string;
  kind: EquationKind;
  /** Display equations only; inline math is never numbered. */
  numbered: boolean;
}

function equationKind(node: PMNode): EquationKind | null {
  if (node.type.name === "blockMath") return "block";
  if (node.type.name === "inlineMath") return "inline";
  return null;
}

function readEquation(node: PMNode, pos: number, kind: EquationKind): SelectedEquation {
  return {
    pos,
    latex: String(node.attrs.latex ?? ""),
    kind,
    numbered: kind === "block" && Boolean(node.attrs.numbered),
  };
}

/** Read the selected equation, if the selection is exactly one math node. */
export function selectedEquation(state: EditorState): SelectedEquation | null {
  const { selection } = state;
  if (!(selection instanceof NodeSelection)) return null;
  const kind = equationKind(selection.node);
  if (!kind) return null;
  return readEquation(selection.node, selection.from, kind);
}

/**
 * Read the equation stored at a position. Returns null when the document
 * changed since the position was captured, so a dialog cannot edit another node.
 */
export function equationAt(state: EditorState, pos: number): SelectedEquation | null {
  // `nodeAt` throws for positions outside the document, so bound it first.
  if (!Number.isInteger(pos) || pos < 0 || pos >= state.doc.content.size) return null;
  const node = state.doc.nodeAt(pos);
  if (!node) return null;
  const kind = equationKind(node);
  if (!kind) return null;
  return readEquation(node, pos, kind);
}

/** Stored document content for one equation. */
export function equationContent(
  latex: string,
  kind: EquationKind = "block",
  numbered = false,
): JSONContent {
  return kind === "inline"
    ? { type: "inlineMath", attrs: { latex } }
    : { type: "blockMath", attrs: { latex, numbered } };
}

/**
 * Render LaTeX locally for the dialog preview. Invalid source is reported
 * instead of inserted, so a broken equation is never saved silently. KaTeX runs
 * with `trust: false`, so the returned markup cannot contain arbitrary links or
 * HTML from the LaTeX source.
 */
export function renderEquationPreview(
  latex: string,
  kind: EquationKind = "block",
): EquationPreview {
  const source = latex.trim();
  if (!source) return { html: null, error: false };
  try {
    return {
      html: katex.renderToString(source, {
        displayMode: kind === "block",
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

/**
 * Display math with an optional equation number. Only the LaTeX source and the
 * `numbered` flag are stored; the number is drawn from a CSS counter in document
 * order, so it updates automatically when equations are added, removed or moved.
 * Numbers are display-only and never leak into the saved LaTeX.
 */
export const NumberedBlockMath = BlockMath.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      numbered: {
        default: false,
        parseHTML: (element) => element.getAttribute("data-numbered") === "true",
        renderHTML: (attributes) =>
          attributes.numbered ? { "data-numbered": "true" } : {},
      },
    };
  },

  addNodeView() {
    const parentAddNodeView = this.parent?.() as
      | NodeViewRenderer
      | null
      | undefined;
    return (props: NodeViewRendererProps) => {
      const view = parentAddNodeView?.(props);
      if (!view) {
        // The parent renderer always exists; a plain element keeps a future
        // upstream change from crashing the editor.
        return { dom: document.createElement("div") };
      }
      const dom = view.dom as HTMLElement;
      const numbered = Boolean(props.node.attrs.numbered);
      dom.classList.toggle("numbered-equation", numbered);
      dom.dataset.numbered = numbered ? "true" : "false";
      return view;
    };
  },
});
