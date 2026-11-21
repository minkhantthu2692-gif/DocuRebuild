import { describe, expect, it } from "vitest";

import {
  buildLanguageOptions,
  confidenceVariant,
  languageLabel,
  preferredSegmentationMode,
} from "@/lib/ocr-display";

describe("OCR display helpers", () => {
  it("colours confidence bands", () => {
    expect(confidenceVariant(null)).toBe("outline");
    expect(confidenceVariant(90)).toBe("success");
    expect(confidenceVariant(85)).toBe("success");
    expect(confidenceVariant(70)).toBe("warning");
    expect(confidenceVariant(60)).toBe("warning");
    expect(confidenceVariant(59)).toBe("destructive");
    expect(confidenceVariant(0)).toBe("destructive");
  });

  it("labels known language codes and passes others through", () => {
    const t = (key: string) => key;
    expect(languageLabel("eng", t)).toBe("ocr.languageEnglish");
    expect(languageLabel("mya", t)).toBe("ocr.languageBurmese");
    expect(languageLabel("fra", t)).toBe("fra");
  });

  it("builds language options from the installed language data", () => {
    const t = (key: string) => key;
    expect(buildLanguageOptions(undefined, t)).toEqual([]);
    expect(buildLanguageOptions([], t)).toEqual([]);
    expect(buildLanguageOptions(["eng"], t)).toEqual([
      { value: "eng", label: "ocr.languageEnglish" },
    ]);
    expect(
      buildLanguageOptions(["eng", "mya"], t).map((option) => option.value),
    ).toEqual(["eng", "mya", "eng+mya"]);
    expect(
      buildLanguageOptions(["fra"], t).map((option) => option.value),
    ).toEqual(["fra"]);
  });

  it("preselects sparse text for Burmese and the configured mode otherwise", () => {
    expect(preferredSegmentationMode("eng", 3)).toBe(3);
    expect(preferredSegmentationMode("fra", 4)).toBe(4);
    expect(preferredSegmentationMode("mya", 3)).toBe(11);
    expect(preferredSegmentationMode("eng+mya", 3)).toBe(11);
    expect(preferredSegmentationMode("eng+mya", 11)).toBe(11);
  });
});
