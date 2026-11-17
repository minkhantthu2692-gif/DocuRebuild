import { Node, mergeAttributes } from "@tiptap/core";

import type { JSONContent } from "@docurebuild/shared-types";

export interface InlineImageContent {
  src: string;
  alt: string;
}

/**
 * An image that lives inside a paragraph instead of breaking the text flow.
 *
 * It stores only the project asset URL and the alt text. Caption, source note
 * and figure numbering belong to the block `figure` node; an inline image is a
 * small in-sentence picture, so none of that is invented here. The node is an
 * atom: text can never be typed inside the image, and deleting the node removes
 * exactly one picture.
 */
export const InlineImageNode = Node.create({
  name: "inlineImage",
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,
  draggable: false,

  addAttributes() {
    return {
      src: {
        default: null,
        parseHTML: (element) => element.getAttribute("src"),
      },
      alt: {
        default: "",
        parseHTML: (element) => element.getAttribute("alt") ?? "",
      },
    };
  },

  parseHTML() {
    return [{ tag: "img[data-doc-inline-image]" }];
  },

  renderHTML({ HTMLAttributes }) {
    const { src, alt } = HTMLAttributes as InlineImageContent;
    return [
      "img",
      mergeAttributes(HTMLAttributes, {
        src: src ?? "",
        alt: alt ?? "",
        class: "doc-inline-image",
        "data-doc-inline-image": "",
        loading: "lazy",
        draggable: "false",
      }),
    ];
  },
});

/**
 * The inline node inserted at the cursor. It is not wrapped in a paragraph, so
 * an insertion inside existing text stays in that sentence; the editor adds a
 * paragraph only when the document has no text block to receive it.
 */
export function inlineImageInsertionContent(image: InlineImageContent): JSONContent[] {
  return [
    {
      type: "inlineImage",
      attrs: {
        src: image.src,
        alt: image.alt,
      },
    },
  ];
}
