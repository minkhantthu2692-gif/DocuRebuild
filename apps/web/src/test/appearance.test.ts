import { beforeEach, describe, expect, it } from "vitest";

import {
  APPEARANCE_STORAGE_KEY,
  applyAppearance,
  cacheAppearance,
  readCachedAppearance,
  resolveTheme,
  DEFAULT_APPEARANCE,
} from "@/lib/appearance";

describe("appearance", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.className = "";
  });

  it("applies design tokens and theme classes to the document root", () => {
    applyAppearance({ ...DEFAULT_APPEARANCE, theme: "dark", accent: "rose", density: "compact" });
    const root = document.documentElement;
    expect(root.dataset.accent).toBe("rose");
    expect(root.dataset.density).toBe("compact");
    expect(root.dataset.fontSize).toBe("md");
    expect(root.classList.contains("dark")).toBe(true);
  });

  it("resolves explicit themes before consulting the system", () => {
    expect(resolveTheme("light")).toBe("light");
    expect(resolveTheme("dark")).toBe("dark");
    expect(resolveTheme("system")).toBe("light");
  });

  it("round-trips cached appearance and tolerates corrupt data", () => {
    cacheAppearance({ ...DEFAULT_APPEARANCE, accent: "teal" });
    expect(readCachedAppearance()?.accent).toBe("teal");

    localStorage.setItem(APPEARANCE_STORAGE_KEY, "{not json");
    expect(readCachedAppearance()).toBeNull();
  });
});
