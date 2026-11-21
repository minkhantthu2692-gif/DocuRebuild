export type ConfidenceVariant = "outline" | "success" | "warning" | "destructive";

/** Shared confidence colouring for OCR and region text. */
export function confidenceVariant(value: number | null): ConfidenceVariant {
  if (value === null) return "outline";
  if (value >= 85) return "success";
  if (value >= 60) return "warning";
  return "destructive";
}

export function languageLabel(code: string, t: (key: string) => string): string {
  if (code === "eng") return t("ocr.languageEnglish");
  if (code === "mya") return t("ocr.languageBurmese");
  return code;
}

/**
 * Page layout to preselect for a language combination.
 *
 * Tesseract's automatic layout analysis collapses Burmese rows, so a combination
 * that includes `mya` starts on sparse text (11). The selector shows the value,
 * and any manual choice stops this preset from overriding it.
 */
export function preferredSegmentationMode(value: string, configured: number): number {
  return value.split("+").includes("mya") ? 11 : configured;
}

/** Recognition options built from installed engine language data. */
export function buildLanguageOptions(
  languages: string[] | undefined,
  t: (key: string) => string,
): Array<{ value: string; label: string }> {
  if (!languages) return [];
  const installed = new Set(languages);
  const options: Array<{ value: string; label: string }> = [];
  if (installed.has("eng")) {
    options.push({ value: "eng", label: t("ocr.languageEnglish") });
  }
  if (installed.has("mya")) {
    options.push({ value: "mya", label: t("ocr.languageBurmese") });
  }
  if (installed.has("eng") && installed.has("mya")) {
    options.push({ value: "eng+mya", label: t("ocr.languageMixed") });
  }
  for (const code of languages) {
    if (code !== "eng" && code !== "mya") {
      options.push({ value: code, label: code });
    }
  }
  return options;
}
