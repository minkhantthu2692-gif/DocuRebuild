import { describe, expect, it } from "vitest";

import type { RegionProposalReason } from "@docurebuild/shared-types";

import { NAMESPACES, resources } from "@/i18n";

const PROPOSAL_REASONS: Record<RegionProposalReason, true> = {
  table_text_grid: true,
  equation_text: true,
  figure_caption_gap: true,
  pdf_image_region: true,
  pdf_drawing_region: true,
  page_artwork_region: true,
  ai_vision: true,
};

function collectKeys(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null) return [prefix];
  return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
    collectKeys(child, prefix ? `${prefix}.${key}` : key),
  );
}

function collectValues(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (typeof value !== "object" || value === null) return [];
  return Object.values(value as Record<string, unknown>).flatMap(collectValues);
}

describe("localization resources", () => {
  it("registers every namespace for both supported languages", () => {
    expect(Object.keys(resources.en).sort()).toEqual([...NAMESPACES].sort());
    expect(Object.keys(resources.my).sort()).toEqual([...NAMESPACES].sort());
  });

  it.each(NAMESPACES)("keeps Burmese and English keys in sync for %s", (namespace) => {
    const enKeys = collectKeys(resources.en[namespace]).sort();
    const myKeys = collectKeys(resources.my[namespace]).sort();
    expect(myKeys).toEqual(enKeys);
  });

  it.each(NAMESPACES)("does not ship empty translations in %s", (namespace) => {
    for (const value of collectValues(resources.en[namespace])) {
      expect(value.trim().length).toBeGreaterThan(0);
    }
    for (const value of collectValues(resources.my[namespace])) {
      expect(value.trim().length).toBeGreaterThan(0);
    }
  });
});

describe("region suggestion sources", () => {
  it("names the source of every proposal reason in both languages", () => {
    for (const reason of Object.keys(PROPOSAL_REASONS)) {
      for (const locale of ["en", "my"] as const) {
        const label =
          resources[locale].workspace.elements.proposals.source[
            reason as RegionProposalReason
          ];
        expect(typeof label).toBe("string");
        expect(label.trim().length).toBeGreaterThan(0);
      }
    }
  });

  it("keeps the prefilled suggestion notice tied to the source label", () => {
    for (const locale of ["en", "my"] as const) {
      const notice = resources[locale].workspace.elements.proposals.prefilledFrom;
      expect(notice).toContain("{{source}}");
    }
  });
});
