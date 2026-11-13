import { Node, mergeAttributes } from "@tiptap/core";
import type { DOMOutputSpec, Node as PMNode } from "@tiptap/pm/model";
import { NodeSelection } from "@tiptap/pm/state";
import type { EditorState } from "@tiptap/pm/state";

import type { JSONContent } from "@docurebuild/shared-types";

export interface FigureContent {
  /** Stable node id used by figure references; generated on insertion. */
  figureId?: string | null;
  src: string;
  alt: string;
  caption: string;
  note: string | null;
  width: number | null;
  height: number | null;
  /** Display-only figure number; the caption text itself is never rewritten. */
  numbered?: boolean;
}

/** A figure the cursor has selected, with the position needed to edit it. */
export interface SelectedFigure {
  pos: number;
  id: string | null;
  caption: string;
  alt: string;
  note: string | null;
  numbered: boolean;
}

function readFigure(node: PMNode, pos: number): SelectedFigure {
  return {
    pos,
    id: typeof node.attrs.id === "string" && node.attrs.id ? node.attrs.id : null,
    caption: String(node.attrs.caption ?? ""),
    alt: String(node.attrs.alt ?? ""),
    note: node.attrs.note ? String(node.attrs.note) : null,
    numbered: Boolean(node.attrs.numbered),
  };
}

/**
 * A stable id for a new figure. `crypto.randomUUID` is available in browsers and
 * modern jsdom; the fallback keeps insertion working in older test environments.
 */
export function createFigureId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `figure-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Read the selected figure, if any. Only a real node selection counts, so a
 * collapsed cursor near a figure can never rewrite its caption.
 */
export function selectedFigure(state: EditorState): SelectedFigure | null {
  const { selection } = state;
  if (!(selection instanceof NodeSelection) || selection.node.type.name !== "figure") {
    return null;
  }
  return readFigure(selection.node, selection.from);
}

/**
 * Read the figure stored at a position. Returns null when the document changed
 * since the position was captured, so a dialog cannot edit a different node.
 */
export function figureAt(state: EditorState, pos: number): SelectedFigure | null {
  // `nodeAt` throws for positions outside the document, so bound it first.
  if (!Number.isInteger(pos) || pos < 0 || pos >= state.doc.content.size) return null;
  const node = state.doc.nodeAt(pos);
  if (!node || node.type.name !== "figure") return null;
  return readFigure(node, pos);
}

function numberAttribute(element: Element, name: string): number | null {
  const value = Number(element.getAttribute(name));
  return Number.isFinite(value) && value > 0 ? value : null;
}

/**
 * A block-level figure that keeps extracted pixels and their caption in the
 * document. It is an atom so the image can never be partially edited, and the
 * original crop remains available in the project after insertion.
 */
export const FigureNode = Node.create({
  name: "figure",
  group: "block",
  atom: true,
  draggable: true,
  selectable: true,

  addAttributes() {
    return {
      id: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-figure-id"),
        renderHTML: (attributes) =>
          attributes.id ? { "data-figure-id": String(attributes.id) } : {},
      },
      src: {
        default: null,
        parseHTML: (element) => element.querySelector("img")?.getAttribute("src") ?? null,
      },
      alt: {
        default: "",
        parseHTML: (element) => element.querySelector("img")?.getAttribute("alt") ?? "",
      },
      caption: {
        default: "",
        parseHTML: (element) =>
          element.querySelector("[data-figure-caption]")?.textContent ?? "",
      },
      note: {
        default: null,
        parseHTML: (element) =>
          element.querySelector("[data-figure-note]")?.textContent ?? null,
      },
      width: {
        default: null,
        parseHTML: (element) => {
          const image = element.querySelector("img");
          return image ? numberAttribute(image, "width") : null;
        },
      },
      height: {
        default: null,
        parseHTML: (element) => {
          const image = element.querySelector("img");
          return image ? numberAttribute(image, "height") : null;
        },
      },
      numbered: {
        default: false,
        parseHTML: (element) => element.getAttribute("data-numbered") === "true",
        renderHTML: (attributes) =>
          attributes.numbered ? { "data-numbered": "true" } : {},
      },
    };
  },

  parseHTML() {
    return [{ tag: "figure[data-doc-figure]" }];
  },

  renderHTML({ HTMLAttributes }) {
    const { src, alt, caption, note, width, height } =
      HTMLAttributes as FigureContent;
    const image: Record<string, string> = {
      src: src ?? "",
      alt: alt ?? "",
      loading: "lazy",
      draggable: "false",
    };
    if (width) image.width = String(width);
    if (height) image.height = String(height);

    // `numbered` has its own renderHTML hook, so it arrives as `data-numbered`
    // rather than as a raw attribute value.
    const showNumber = HTMLAttributes["data-numbered"] === "true";
    const captionChildren: DOMOutputSpec[] = [];
    if (caption || showNumber) {
      const label: DOMOutputSpec[] = showNumber
        ? [["span", { "data-figure-label": "" }]]
        : [];
      captionChildren.push([
        "span",
        { "data-figure-caption": "" },
        ...label,
        caption,
      ]);
    }
    if (note) {
      captionChildren.push(["span", { "data-figure-note": "" }, note]);
    }

    const children: DOMOutputSpec[] = [["img", image]];
    if (captionChildren.length > 0) {
      children.push(["figcaption", {}, ...captionChildren]);
    }

    return [
      "figure",
      mergeAttributes(HTMLAttributes, { "data-doc-figure": "", class: "doc-figure" }),
      ...children,
    ];
  },
});

/**
 * Convert an extracted element into the single block node inserted into the
 * document. The caption and source note stay separate so a missing caption
 * never hides where the pixels came from.
 */
export function figureInsertionContent(figure: FigureContent): JSONContent[] {
  return [
    {
      type: "figure",
      attrs: {
        id: figure.figureId ?? createFigureId(),
        src: figure.src,
        alt: figure.alt,
        caption: figure.caption,
        note: figure.note,
        width: figure.width,
        height: figure.height,
        ...(figure.numbered ? { numbered: true } : {}),
      },
    },
  ];
}
