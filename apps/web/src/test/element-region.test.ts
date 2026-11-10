import { describe, expect, it } from "vitest";

import { displayRect, selectionToSourceRect } from "@/lib/element-region";

const frame = {
  left: 20,
  top: 10,
  width: 400,
  height: 300,
  naturalWidth: 1200,
  naturalHeight: 900,
};

describe("selectionToSourceRect", () => {
  it("scales a rendered marquee back to source pixels", () => {
    const rect = selectionToSourceRect({ x: 220, y: 160 }, { x: 420, y: 310 }, frame);
    expect(rect).toEqual({ x: 600, y: 450, width: 600, height: 450 });
  });

  it("supports dragging in any direction", () => {
    const forward = selectionToSourceRect({ x: 220, y: 160 }, { x: 420, y: 310 }, frame);
    const backward = selectionToSourceRect({ x: 420, y: 310 }, { x: 220, y: 160 }, frame);
    expect(backward).toEqual(forward);
  });

  it("clamps a marquee that leaves the image", () => {
    const rect = selectionToSourceRect({ x: -100, y: -100 }, { x: 100, y: 100 }, frame);
    expect(rect).toEqual({ x: 0, y: 0, width: 240, height: 270 });
  });

  it("rejects selections that are too small or have no frame", () => {
    expect(selectionToSourceRect({ x: 100, y: 100 }, { x: 101, y: 101 }, frame)).toBeNull();
    expect(selectionToSourceRect({ x: 100, y: 100 }, { x: 200, y: 200 }, null)).toBeNull();
  });
});

describe("displayRect", () => {
  it("normalizes a drag in any direction", () => {
    expect(displayRect({ x: 30, y: 50 }, { x: 10, y: 20 })).toEqual({
      left: 10,
      top: 20,
      width: 20,
      height: 30,
    });
  });
});
