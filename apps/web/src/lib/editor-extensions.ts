import Placeholder from "@tiptap/extension-placeholder";
import { TableKit } from "@tiptap/extension-table";
import TextAlign from "@tiptap/extension-text-align";
import StarterKit from "@tiptap/starter-kit";

import { FigureNode } from "./editor-figure";
import { normalizeLinkUrl } from "./link";

/**
 * One extension list for the workspace editor and the editor tests, so a table
 * or node cannot work in a test while being missing from the real editor.
 */
export function createEditorExtensions(placeholder: () => string) {
  return [
    StarterKit.configure({
      heading: { levels: [1, 2, 3] },
      underline: {},
      link: {
        openOnClick: false,
        autolink: true,
        linkOnPaste: true,
        HTMLAttributes: {
          rel: "noopener noreferrer nofollow",
          target: "_blank",
        },
        // Pasted and auto-detected links must follow the same policy as the
        // dialog, otherwise a non-http target could enter around it.
        isAllowedUri: (url) => normalizeLinkUrl(url) !== null,
      },
    }),
    TextAlign.configure({ types: ["heading", "paragraph"] }),
    // Column resizing is deliberately off: stored pixel widths would make the
    // document layout depend on one screen size, and Markdown cannot keep them.
    TableKit.configure({
      table: {
        resizable: false,
        HTMLAttributes: { class: "doc-table" },
      },
    }),
    FigureNode,
    Placeholder.configure({ placeholder }),
  ];
}
