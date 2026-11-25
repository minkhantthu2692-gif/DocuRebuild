import type { FontFaceSummary, FontFamilySummary, JSONContent } from "@docurebuild/shared-types";

import { api } from "@/lib/api";

/**
 * Imported fonts are bytes stored by the local backend, so they cannot be
 * referenced with a plain CSS URL: the desktop API requires its launch token.
 * They are fetched once and registered through the FontFace API instead.
 */
const loadedFaces = new Set<string>();
const pendingFaces = new Map<string, Promise<void>>();

export function sanitizeFontFamily(value: unknown): string {
  if (typeof value !== "string") return "";
  return value
    .replace(/["'`\\{}<>;]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 160);
}

export function cssFontFamily(value: string): string {
  return `"${sanitizeFontFamily(value)}"`;
}

export function collectFontFamilies(content: unknown): string[] {
  const found = new Map<string, string>();

  const walk = (value: unknown): void => {
    if (Array.isArray(value)) {
      value.forEach(walk);
      return;
    }
    if (!value || typeof value !== "object") return;
    const node = value as JSONContent;
    for (const mark of node.marks ?? []) {
      if (!mark || typeof mark !== "object") continue;
      if (mark.type !== "textStyle") continue;
      const attrs = mark.attrs;
      if (!attrs || typeof attrs !== "object") continue;
      const family = sanitizeFontFamily(attrs.fontFamily);
      if (!family) continue;
      const key = family.toLocaleLowerCase();
      if (!found.has(key)) found.set(key, family);
    }
    if (Array.isArray(node.content)) node.content.forEach(walk);
  };

  walk(content);
  return [...found.values()];
}

async function loadFace(face: FontFaceSummary): Promise<void> {
  if (!face.id) return;
  if (loadedFaces.has(face.id)) return;
  const pending = pendingFaces.get(face.id);
  if (pending) return pending;

  const job = (async () => {
    if (typeof document === "undefined" || !document.fonts) return;
    const data = await api.getFontFile(face.id as string);
    const fontFace = new FontFace(cssFontFamily(face.family), data, {
      weight: String(face.weight),
      style: face.italic ? "italic" : "normal",
      display: "swap",
    });
    await fontFace.load();
    document.fonts.add(fontFace);
    loadedFaces.add(face.id as string);
  })();

  pendingFaces.set(face.id, job);
  try {
    await job;
  } finally {
    pendingFaces.delete(face.id);
  }
}

export interface FontLoadResult {
  /** Families the document refers to that this device cannot render. */
  missing: string[];
}

export async function ensureImportedFontsLoaded(
  families: FontFamilySummary[],
  names: string[],
): Promise<FontLoadResult> {
  const wanted = [...new Set(names.map(sanitizeFontFamily).filter(Boolean))];
  if (wanted.length === 0) return { missing: [] };

  const catalogue = new Map(
    families.map((family) => [family.name.toLocaleLowerCase(), family]),
  );
  const loaded = new Map<string, boolean>();
  const jobs: Promise<void>[] = [];

  for (const name of wanted) {
    const family = catalogue.get(name.toLocaleLowerCase());
    if (!family) continue;
    for (const face of family.faces) {
      if (face.source !== "imported" || !face.id) continue;
      const key = name.toLocaleLowerCase();
      jobs.push(
        loadFace(face)
          .then(() => {
            loaded.set(key, true);
          })
          .catch(() => {
            // A missing file is reported through the missing list below.
          }),
      );
    }
  }
  await Promise.all(jobs);

  const missing = wanted.filter((name) => {
    const family = catalogue.get(name.toLocaleLowerCase());
    if (!family) return true;
    // A system or mixed family can still be rendered by the platform even when
    // one imported face failed to download.
    if (family.faces.some((face) => face.source === "system")) return false;
    return !loaded.get(name.toLocaleLowerCase());
  });
  return { missing };
}
