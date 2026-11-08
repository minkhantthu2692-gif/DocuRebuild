import { describe, expect, it } from "vitest";

import {
  DEFAULT_WORKSPACE_LAYOUT,
  MAX_SPLIT,
  MIN_SPLIT,
  WORKSPACE_LAYOUT_KEY,
  clampSplit,
  normalizeLayout,
  readWorkspaceLayout,
  writeWorkspaceLayout,
} from "@/lib/workspace-layout";

describe("workspace layout", () => {
  it("clamps the split to a usable range", () => {
    expect(clampSplit(0.1)).toBe(MIN_SPLIT);
    expect(clampSplit(0.9)).toBe(MAX_SPLIT);
    expect(clampSplit(Number.NaN)).toBe(DEFAULT_WORKSPACE_LAYOUT.split);
  });

  it("never hides both panels", () => {
    const layout = normalizeLayout({
      sourceVisible: false,
      editorVisible: false,
      split: 0.5,
    });
    expect(layout.sourceVisible).toBe(true);
    expect(layout.editorVisible).toBe(false);
  });

  it("persists and restores a layout", () => {
    localStorage.clear();
    writeWorkspaceLayout({ sourceVisible: true, editorVisible: false, split: 0.55 });
    expect(readWorkspaceLayout()).toEqual({
      sourceVisible: true,
      editorVisible: false,
      split: 0.55,
    });
  });

  it("falls back to defaults for missing or corrupt values", () => {
    localStorage.clear();
    expect(readWorkspaceLayout()).toEqual(DEFAULT_WORKSPACE_LAYOUT);

    localStorage.setItem(WORKSPACE_LAYOUT_KEY, "{bad json");
    expect(readWorkspaceLayout()).toEqual(DEFAULT_WORKSPACE_LAYOUT);
  });
});
