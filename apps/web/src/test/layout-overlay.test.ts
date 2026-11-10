import { describe, expect, it } from "vitest";

import type { OcrBlock, OcrBlockKind } from "@docurebuild/shared-types";

import { containFrame, layoutBoxes, type ImageFrame } from "@/lib/layout-overlay";

function block(
  overrides: Partial<OcrBlock> & { id: string },
  kind: OcrBlockKind = "paragraph",
): OcrBlock {
  return {
    run_id: "run-1",
    page_id: "page-1",
    block_index: 0,
    kind,
    text: "text",
    confidence: 90,
    x: 0,
    y: 0,
    width: 10,
    height: 10,
    line_count: 1,
    word_count: 1,
    verified: false,
    corrected: false,
    created_at: "2026-11-10T00:00:00Z",
    updated_at: "2026-11-10T00:00:00Z",
    ...overrides,
  };
}

const frame: ImageFrame = {
  left: 0,
  top: 0,
  width: 500,
  height: 1000,
  naturalWidth: 1000,
  naturalHeight: 2000,
};

describe("layoutBoxes", () => {
  it("scales source pixels into rendered pixels", () => {
    const boxes = layoutBoxes(
      [block({ id: "a", x: 100, y: 200, width: 300, height: 50 }, "heading")],
      frame,
    );

    expect(boxes).toEqual([
      { id: "a", kind: "heading", left: 50, top: 100, width: 150, height: 25 },
    ]);
  });

  it("keeps boxes relative to the image origin regardless of the frame offset", () => {
    const shifted = { ...frame, left: 240, top: 120 };
    const boxes = layoutBoxes([block({ id: "a", x: 100, y: 200, width: 100, height: 100 })], shifted);

    expect(boxes[0]).toMatchObject({ left: 50, top: 100, width: 50, height: 50 });
  });

  it("clamps geometry that extends past the source image", () => {
    const boxes = layoutBoxes(
      [block({ id: "a", x: 900, y: 1900, width: 400, height: 400 })],
      frame,
    );

    expect(boxes).toEqual([
      { id: "a", kind: "paragraph", left: 450, top: 950, width: 50, height: 50 },
    ]);
  });

  it("skips blocks without usable geometry", () => {
    const boxes = layoutBoxes(
      [
        block({ id: "missing", x: null }),
        block({ id: "zero", width: 0 }),
        block({ id: "outside", x: 1000, y: 0, width: 20, height: 20 }),
        block({ id: "negative", x: -50, y: -50, width: 20, height: 20 }),
        block({ id: "ok", x: 0, y: 0, width: 100, height: 100 }),
      ],
      frame,
    );

    expect(boxes.map((box) => box.id)).toEqual(["ok"]);
  });

  it("returns nothing when the rendered frame is not measurable", () => {
    expect(layoutBoxes([block({ id: "a" })], { ...frame, width: 0 })).toEqual([]);
    expect(layoutBoxes([block({ id: "a" })], { ...frame, naturalHeight: 0 })).toEqual([]);
  });
});

describe("containFrame", () => {
  it("centres a letterboxed image inside the measured box", () => {
    const result = containFrame(
      { left: 10, top: 20, width: 400, height: 400 },
      1000,
      2000,
    );

    expect(result).toEqual({
      left: 110,
      top: 20,
      width: 200,
      height: 400,
      naturalWidth: 1000,
      naturalHeight: 2000,
    });
  });

  it("rejects unmeasurable images", () => {
    expect(containFrame({ left: 0, top: 0, width: 0, height: 100 }, 10, 10)).toBeNull();
    expect(containFrame({ left: 0, top: 0, width: 100, height: 100 }, 0, 10)).toBeNull();
  });
});
