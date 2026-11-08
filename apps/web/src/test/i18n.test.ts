import { describe, expect, it } from "vitest";

import { NAMESPACES, resources } from "@/i18n";

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
