import { describe, expect, it } from "vitest";

import { figureInsertionContent } from "@/lib/editor-figure";

describe("figureInsertionContent", () => {
  it("wraps an extracted region in a single block node", () => {
    const [node] = figureInsertionContent({
      src: "/api/projects/p/assets/a/file",
      alt: "Figure 1",
      caption: "Figure 1. Phase diagram",
      note: "Source: page 4 · manual region · Unverified",
      width: 320,
      height: 180,
    });

    expect(node.type).toBe("figure");
    expect(node.attrs).toMatchObject({
      src: "/api/projects/p/assets/a/file",
      alt: "Figure 1",
      caption: "Figure 1. Phase diagram",
      note: "Source: page 4 · manual region · Unverified",
      width: 320,
      height: 180,
    });
  });

  it("keeps an empty caption when the user did not provide one", () => {
    const [node] = figureInsertionContent({
      src: "/file",
      alt: "",
      caption: "",
      note: null,
      width: null,
      height: null,
    });
    expect(node.attrs?.caption).toBe("");
    expect(node.attrs?.note).toBeNull();
  });
});
