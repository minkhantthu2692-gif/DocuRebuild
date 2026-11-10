import { Node } from "@tiptap/core";
import type { DOMOutputSpec } from "@tiptap/pm/model";

import type { JSONContent } from "@docurebuild/shared-types";

export interface FigureContent {
  src: string;
  alt: string;
  caption: string;
  note: string | null;
  width: number | null;
  height: number | null;
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
    };
  },

  parseHTML() {
    return [{ tag: "figure[data-doc-figure]" }];
  },

  renderHTML({ HTMLAttributes }) {
    const { src, alt, caption, note, width, height } = HTMLAttributes as FigureContent;

    const image: Record<string, string> = {
      src: src ?? "",
      alt: alt ?? "",
      loading: "lazy",
      draggable: "false",
    };
    if (width) image.width = String(width);
    if (height) image.height = String(height);

    const captionChildren: DOMOutputSpec[] = [];
    if (caption) {
      captionChildren.push(["span", { "data-figure-caption": "" }, caption]);
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
      { "data-doc-figure": "", class: "doc-figure" },
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
        src: figure.src,
        alt: figure.alt,
        caption: figure.caption,
        note: figure.note,
        width: figure.width,
        height: figure.height,
      },
    },
  ];
}
