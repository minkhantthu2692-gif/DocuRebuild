/**
 * Locale-aware text statistics for the document editor.
 * Uses Intl.Segmenter where available so Burmese and other scripts that do not
 * separate words with spaces are counted sensibly.
 */
export function countWords(text: string, locale: string): number {
  const trimmed = text.trim();
  if (!trimmed) return 0;

  if (typeof Intl.Segmenter === "function") {
    const segmenter = new Intl.Segmenter(locale, { granularity: "word" });
    let count = 0;
    for (const segment of segmenter.segment(trimmed)) {
      if (segment.isWordLike) count += 1;
    }
    return count;
  }

  return trimmed.split(/\s+/u).length;
}

/** Counts Unicode code points, so emoji and combining marks count as characters. */
export function countCharacters(text: string): number {
  return Array.from(text).length;
}
