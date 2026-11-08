import { describe, expect, it } from "vitest";

import { countCharacters, countWords } from "@/lib/text";

describe("text statistics", () => {
  it("counts words in space-separated text", () => {
    expect(countWords("The Schrödinger equation", "en-US")).toBe(3);
    expect(countWords("  \n\t ", "en-US")).toBe(0);
  });

  it("counts Burmese text as words rather than one long token", () => {
    expect(countWords("မြန်မာစာ စမ်းသပ်ချက်", "my-MM")).toBeGreaterThan(1);
  });

  it("counts Unicode code points instead of UTF-16 units", () => {
    expect(countCharacters("abc")).toBe(3);
    expect(countCharacters("မြန်မာ")).toBe(6);
    expect(countCharacters("📄")).toBe(1);
  });
});
