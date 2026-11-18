/**
 * Local text diff used by the version comparison view and by AI proposal review.
 *
 * Every comparison is read-only and deterministic: it never changes a document
 * and it never calls a provider. Long unchanged runs are collapsed around the
 * changed lines so a small edit in a long document stays readable.
 */

export const DIFF_CONTEXT_LINES = 2;

/** Changed-line budget before the comparison reports that it is too large. */
const MAX_DIFF_LINES = 5_000;
/** Maximum LCS table cells; keeps the worst case bounded in time and memory. */
const MAX_DIFF_CELLS = 1_000_000;

export type DiffLineKind = "same" | "added" | "removed";

export interface DiffLine {
  kind: DiffLineKind;
  text: string;
}

/** A collapsed run of unchanged lines, so long documents stay readable. */
export interface DiffGap {
  kind: "gap";
  count: number;
}

export type DiffRow = DiffLine | DiffGap;

export interface DiffResult {
  /** True when both texts contain the same lines (line endings are normalised). */
  identical: boolean;
  /** True when the changed region is too large to compare here. */
  tooLarge: boolean;
  added: number;
  removed: number;
  rows: DiffRow[];
}

function splitLines(text: string): string[] {
  if (text === "") return [];
  return text.replace(/\r\n?/g, "\n").split("\n");
}

/** Classic longest-common-subsequence diff over lines. */
function diffLineArrays(before: string[], after: string[]): DiffLine[] {
  const n = before.length;
  const m = after.length;
  const width = m + 1;
  const table = new Uint32Array((n + 1) * width);

  for (let i = n - 1; i >= 0; i -= 1) {
    const row = i * width;
    const next = (i + 1) * width;
    for (let j = m - 1; j >= 0; j -= 1) {
      table[row + j] =
        before[i] === after[j]
          ? table[next + j + 1] + 1
          : Math.max(table[next + j], table[row + j + 1]);
    }
  }

  const lines: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (before[i] === after[j]) {
      lines.push({ kind: "same", text: before[i] });
      i += 1;
      j += 1;
    } else if (table[(i + 1) * width + j] >= table[i * width + j + 1]) {
      lines.push({ kind: "removed", text: before[i] });
      i += 1;
    } else {
      lines.push({ kind: "added", text: after[j] });
      j += 1;
    }
  }
  while (i < n) {
    lines.push({ kind: "removed", text: before[i] });
    i += 1;
  }
  while (j < m) {
    lines.push({ kind: "added", text: after[j] });
    j += 1;
  }
  return lines;
}

/** Replace long unchanged runs with a gap while keeping `context` lines around them. */
function collapseUnchanged(lines: DiffLine[], context: number): DiffRow[] {
  const rows: DiffRow[] = [];
  let index = 0;
  while (index < lines.length) {
    if (lines[index].kind !== "same") {
      rows.push(lines[index]);
      index += 1;
      continue;
    }

    let end = index;
    while (end < lines.length && lines[end].kind === "same") end += 1;
    const run = end - index;
    if (run <= context * 2 + 1) {
      rows.push(...lines.slice(index, end));
    } else {
      rows.push(...lines.slice(index, index + context));
      rows.push({ kind: "gap", count: run - context * 2 });
      rows.push(...lines.slice(end - context, end));
    }
    index = end;
  }
  return rows;
}

/** One run of equal, removed or added characters in an inline comparison. */
export type InlineDiffKind = "same" | "removed" | "added";

export interface InlineDiffSegment {
  kind: InlineDiffKind;
  text: string;
}

export interface InlineDiff {
  /** True when both strings contain exactly the same characters. */
  identical: boolean;
  /** True when the changed middle was too large to align precisely. */
  coarse: boolean;
  /** Number of grapheme clusters only in `before`. */
  removed: number;
  /** Number of grapheme clusters only in `after`. */
  added: number;
  segments: InlineDiffSegment[];
}

/** Maximum LCS cells for an inline comparison; the worst case stays bounded. */
const MAX_INLINE_CELLS = 160_000;

let graphemeSegmenter: Intl.Segmenter | null | undefined;

/** Split by grapheme clusters when available, so a combining mark stays attached. */
function splitGraphemes(text: string): string[] {
  if (graphemeSegmenter === undefined) {
    graphemeSegmenter =
      typeof Intl !== "undefined" && "Segmenter" in Intl
        ? new Intl.Segmenter(undefined, { granularity: "grapheme" })
        : null;
  }
  if (!graphemeSegmenter) return Array.from(text);
  return Array.from(graphemeSegmenter.segment(text), (part) => part.segment);
}

/**
 * Character-level diff for a short proposal, used only for display.
 *
 * It is deterministic, read-only and never contacts a provider. Common prefixes
 * and suffixes are trimmed first, so a small correction in a long block stays
 * cheap. When the changed middle is still too large to align, the whole middle is
 * reported as one removal plus one addition and `coarse` is set, which keeps a
 * poorly written proposal from freezing the review dialog.
 */
export function diffInlineText(before: string, after: string): InlineDiff {
  if (before === after) {
    return {
      identical: true,
      coarse: false,
      removed: 0,
      added: 0,
      // Still return the text as one unchanged run so a view can render it.
      segments: before === "" ? [] : [{ kind: "same", text: before }],
    };
  }

  const beforeChars = splitGraphemes(before);
  const afterChars = splitGraphemes(after);

  let prefix = 0;
  while (
    prefix < beforeChars.length &&
    prefix < afterChars.length &&
    beforeChars[prefix] === afterChars[prefix]
  ) {
    prefix += 1;
  }

  let suffix = 0;
  while (
    suffix < beforeChars.length - prefix &&
    suffix < afterChars.length - prefix &&
    beforeChars[beforeChars.length - 1 - suffix] === afterChars[afterChars.length - 1 - suffix]
  ) {
    suffix += 1;
  }

  const segments: InlineDiffSegment[] = [];
  const push = (kind: InlineDiffKind, text: string) => {
    if (!text) return;
    const last = segments[segments.length - 1];
    if (last && last.kind === kind) {
      last.text += text;
      return;
    }
    segments.push({ kind, text });
  };

  push("same", beforeChars.slice(0, prefix).join(""));

  const middleBefore = beforeChars.slice(prefix, beforeChars.length - suffix);
  const middleAfter = afterChars.slice(prefix, afterChars.length - suffix);
  let coarse = false;

  if (middleBefore.length === 0) {
    push("added", middleAfter.join(""));
  } else if (middleAfter.length === 0) {
    push("removed", middleBefore.join(""));
  } else if (middleBefore.length * middleAfter.length > MAX_INLINE_CELLS) {
    coarse = true;
    push("removed", middleBefore.join(""));
    push("added", middleAfter.join(""));
  } else {
    for (const line of diffLineArrays(middleBefore, middleAfter)) {
      push(line.kind, line.text);
    }
  }

  push("same", beforeChars.slice(beforeChars.length - suffix).join(""));

  let removed = 0;
  let added = 0;
  for (const segment of segments) {
    if (segment.kind === "removed") removed += splitGraphemes(segment.text).length;
    if (segment.kind === "added") added += splitGraphemes(segment.text).length;
  }

  return { identical: false, coarse, removed, added, segments };
}

export function diffText(
  before: string,
  after: string,
  context: number = DIFF_CONTEXT_LINES,
): DiffResult {
  const safeContext = Math.max(0, Math.floor(context));
  if (before === after) {
    return { identical: true, tooLarge: false, added: 0, removed: 0, rows: [] };
  }

  const beforeLines = splitLines(before);
  const afterLines = splitLines(after);

  let prefix = 0;
  while (
    prefix < beforeLines.length &&
    prefix < afterLines.length &&
    beforeLines[prefix] === afterLines[prefix]
  ) {
    prefix += 1;
  }

  let suffix = 0;
  while (
    suffix < beforeLines.length - prefix &&
    suffix < afterLines.length - prefix &&
    beforeLines[beforeLines.length - 1 - suffix] === afterLines[afterLines.length - 1 - suffix]
  ) {
    suffix += 1;
  }

  const middleBefore = beforeLines.slice(prefix, beforeLines.length - suffix);
  const middleAfter = afterLines.slice(prefix, afterLines.length - suffix);

  if (middleBefore.length + middleAfter.length > MAX_DIFF_LINES) {
    return { identical: false, tooLarge: true, added: 0, removed: 0, rows: [] };
  }

  let middle: DiffLine[];
  if (middleBefore.length === 0) {
    middle = middleAfter.map((text) => ({ kind: "added", text }));
  } else if (middleAfter.length === 0) {
    middle = middleBefore.map((text) => ({ kind: "removed", text }));
  } else if (middleBefore.length * middleAfter.length > MAX_DIFF_CELLS) {
    return { identical: false, tooLarge: true, added: 0, removed: 0, rows: [] };
  } else {
    middle = diffLineArrays(middleBefore, middleAfter);
  }

  const added = middle.filter((line) => line.kind === "added").length;
  const removed = middle.filter((line) => line.kind === "removed").length;
  if (added === 0 && removed === 0) {
    // Only line endings differed; the text itself is unchanged.
    return { identical: true, tooLarge: false, added: 0, removed: 0, rows: [] };
  }

  const lines: DiffLine[] = [
    ...beforeLines.slice(0, prefix).map((text) => ({ kind: "same" as const, text })),
    ...middle,
    ...beforeLines
      .slice(beforeLines.length - suffix)
      .map((text) => ({ kind: "same" as const, text })),
  ];

  return {
    identical: false,
    tooLarge: false,
    added,
    removed,
    rows: collapseUnchanged(lines, safeContext),
  };
}
