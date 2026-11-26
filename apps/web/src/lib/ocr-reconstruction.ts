import type { JSONContent } from "@tiptap/core";
import type { OcrBlockKind, OcrLine } from "@docurebuild/shared-types";

/**
 * The minimum block information paragraph reconstruction needs.
 *
 * `text` is the reviewed text, not necessarily the engine's original text, so
 * a correction made in the review dialog is what gets inserted. Geometry is
 * only used to decide which blocks belong to the same paragraph; it never
 * rewrites characters.
 */
export interface OcrReconstructionBlock {
  kind: OcrBlockKind;
  text: string;
  x: number | null;
  y: number | null;
  width: number | null;
  height: number | null;
  /** Visual line boxes when the engine stored them. */
  lines?: OcrLine[];
}

type GroupClass = "prose" | "heading" | "list" | "verbatim";

/** Sentence-final punctuation, including Burmese and CJK terminators. */
const TERMINAL_RE = /[.!?;:。！？…။।]["'”’)\]]*$/u;
/** A lowercase first character is strong evidence of a wrapped sentence. */
const LOWERCASE_START_RE = /^\p{Ll}/u;
const CONNECTOR_END_RE = /[,;:\-–—]$/u;
/**
 * Scripts that do not put a space between words at a line break. Joining two
 * Myanmar or CJK characters with a space would corrupt the word.
 */
const NO_SPACE_SCRIPT_RE =
  /[\u1000-\u109F\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF\uAC00-\uD7AF]/u;

interface PreparedBlock {
  kind: OcrBlockKind;
  className: GroupClass;
  text: string;
  lines: string[];
  rawLines: string[];
  left: number;
  right: number;
  top: number;
  bottom: number;
  width: number;
  height: number;
  lineCount: number;
  maxLineWidth: number;
  lastLineWidth: number;
  maxLineHeight: number;
  lineHeights: number[];
  hasGeometry: boolean;
  order: number;
}

interface TextGroup {
  className: GroupClass;
  kind: OcrBlockKind;
  text: string;
  lines: string[];
  rawLines: string[];
  left: number;
  right: number;
  top: number;
  bottom: number;
  width: number;
  height: number;
  lineCount: number;
  maxLineWidth: number;
  lastLineWidth: number;
  maxLineHeight: number;
  hasGeometry: boolean;
  /** Every source block merged so far contained a single visual line. */
  allSingleLine: boolean;
}

interface PageMetrics {
  bodyLeft: number;
  bodyRight: number;
  bodyWidth: number;
  lineHeight: number;
}

function median(values: number[]): number {
  const usable = values.filter((value) => Number.isFinite(value) && value > 0);
  if (usable.length === 0) return 0;
  const sorted = [...usable].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle];
}

function splitRawLines(text: string): string[] {
  return text
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .filter((line) => line.trim().length > 0);
}

/**
 * Join two fragments that were split by a visual line break.
 *
 * The only character ever removed is the break itself. A hyphen stays, so an
 * original "recon-" + "struction" becomes "recon-struction" rather than an
 * invented word. Myanmar and CJK fragments are joined without a space because
 * those scripts do not use one at a line break.
 */
function joinText(previous: string, next: string): string {
  const left = previous.trimEnd();
  const right = next.trimStart();
  if (!left) return right;
  if (!right) return left;
  const last = left[left.length - 1];
  const first = right[0];
  if (last === "-") return left + right;
  if (NO_SPACE_SCRIPT_RE.test(last) && NO_SPACE_SCRIPT_RE.test(first)) {
    return left + right;
  }
  return `${left} ${right}`;
}

function joinLines(lines: string[]): string {
  return lines.reduce((result, line) => joinText(result, line), "");
}

function finite(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function prepareBlock(
  block: OcrReconstructionBlock,
  order: number,
): PreparedBlock | null {
  const rawLines = splitRawLines(block.text);
  const lines = rawLines.map((line) => line.trim());
  if (lines.length === 0) return null;

  const x = finite(block.x);
  const y = finite(block.y);
  const width = finite(block.width);
  const height = finite(block.height);
  const hasGeometry = x !== null && y !== null && width !== null && height !== null;

  const geometryLines =
    block.lines &&
    block.lines.length === lines.length &&
    block.lines.every(
      (line) =>
        Number.isFinite(line.width) &&
        Number.isFinite(line.height) &&
        line.width > 0 &&
        line.height > 0,
    )
      ? block.lines
      : [];
  const lineWidths = geometryLines.map((line) => line.width);
  const lineHeights = geometryLines.map((line) => line.height);

  return {
    kind: block.kind,
    className: "prose",
    text: joinLines(lines),
    lines,
    rawLines,
    left: x ?? 0,
    right: (x ?? 0) + (width ?? 0),
    top: y ?? 0,
    bottom: (y ?? 0) + (height ?? 0),
    width: width ?? 0,
    height: height ?? 0,
    lineCount: lines.length,
    maxLineWidth: lineWidths.length > 0 ? Math.max(...lineWidths) : (width ?? 0),
    lastLineWidth:
      lineWidths.length > 0 ? lineWidths[lineWidths.length - 1] : (width ?? 0),
    maxLineHeight:
      lineHeights.length > 0 ? Math.max(...lineHeights) : (height ?? 0),
    lineHeights,
    hasGeometry,
    order,
  };
}

function pageMetrics(blocks: PreparedBlock[]): PageMetrics {
  const withGeometry = blocks.filter((block) => block.hasGeometry);
  const left = withGeometry.length
    ? Math.min(...withGeometry.map((block) => block.left))
    : 0;
  const right = withGeometry.length
    ? Math.max(...withGeometry.map((block) => block.right))
    : 0;

  const heights: number[] = [];
  for (const block of blocks) {
    if (block.lineHeights.length > 0) {
      heights.push(...block.lineHeights);
    } else if (block.lineCount === 1 && block.hasGeometry) {
      heights.push(block.height);
    }
  }
  let lineHeight = median(heights);
  if (lineHeight === 0) {
    lineHeight = median(
      withGeometry.map((block) => block.height / Math.max(block.lineCount, 1)),
    );
  }
  if (lineHeight === 0) lineHeight = 24;

  return {
    bodyLeft: left,
    bodyRight: right,
    bodyWidth: Math.max(0, right - left),
    lineHeight,
  };
}

function classFor(block: PreparedBlock, bodyWidth: number): GroupClass {
  if (block.kind === "table" || block.kind === "equation") return "verbatim";
  if (block.kind === "list_item") return "list";
  if (block.kind !== "heading") return "prose";

  // A long line that spans the body width is body text even when its box is a
  // little taller than the median line (descenders and accents do that).
  const spansBody = bodyWidth > 0 && block.width >= bodyWidth * 0.82;
  const isLong = block.text.length >= 60 || block.text.split(/\s+/).length > 10;
  return spansBody && isLong ? "prose" : "heading";
}

function columnsMatch(
  a: TextGroup,
  b: PreparedBlock,
  tolerance: number,
  indentTolerance = 0,
): boolean {
  const overlap = Math.min(a.right, b.right) - Math.max(a.left, b.left);
  const narrowest = Math.min(a.width, b.width);
  if (narrowest <= 0 || overlap <= 0) return false;
  if (overlap / narrowest < 0.5) return false;
  const leftDelta = Math.abs(a.left - b.left);
  const rightDelta = Math.abs(a.right - b.right);
  return (
    leftDelta <= tolerance ||
    rightDelta <= tolerance ||
    (indentTolerance > 0 && leftDelta <= indentTolerance)
  );
}

function continuesText(previous: string, next: string): boolean {
  if (!previous || !next) return false;
  if (TERMINAL_RE.test(previous)) return false;
  if (LOWERCASE_START_RE.test(next)) return true;
  return CONNECTOR_END_RE.test(previous);
}

function findMergeTarget(
  groups: TextGroup[],
  block: PreparedBlock,
  lineHeight: number,
): TextGroup | null {
  if (!block.hasGeometry) return null;
  const tolerance = Math.max(lineHeight * 0.75, 8);
  let best: TextGroup | null = null;
  let bestGap = Number.POSITIVE_INFINITY;

  for (const group of groups) {
    if (!group.hasGeometry) continue;
    if (group.className === "verbatim") continue;

    // A wrapped list item can be split into a marker line and an unmarked
    // continuation block. Attach that block to the list item instead of
    // leaving it as a stray paragraph.
    const listContinuation =
      group.className === "list" &&
      block.className === "prose" &&
      !TERMINAL_RE.test(group.text) &&
      (LOWERCASE_START_RE.test(block.text) ||
        CONNECTOR_END_RE.test(group.text));
    const sameClass = group.className === block.className;
    if (!sameClass && !listContinuation) continue;
    // Two list blocks are separate items. They are combined later by the list
    // builder, never merged into one text run.
    if (sameClass && group.className === "list") continue;

    const gap = block.top - group.bottom;
    if (gap < -lineHeight * 0.6) continue;
    if (gap > lineHeight * 1.25) continue;
    if (
      !columnsMatch(group, block, tolerance, lineHeight * 2.5)
    ) {
      continue;
    }

    if (listContinuation) {
      if (gap <= lineHeight * 0.8 && gap < bestGap) {
        best = group;
        bestGap = gap;
      }
      continue;
    }

    const tightGap = lineHeight * 0.8;
    const bothSingleLine = group.allSingleLine && block.lineCount === 1;
    const continues = continuesText(group.text, block.text);
    const unfinished = !TERMINAL_RE.test(group.text);
    const shortLastLine =
      group.lineCount > 1 &&
      group.maxLineWidth > 0 &&
      group.lastLineWidth < group.maxLineWidth * 0.8;
    const fullLastLine =
      group.lineCount <= 1 ||
      group.maxLineWidth <= 0 ||
      group.lastLineWidth >= group.maxLineWidth * 0.8;

    let mergeable = false;
    if (gap <= tightGap) {
      // Sparse segmentation (PSM 11) emits one block per visual line. Adjacent
      // single lines inside a paragraph can end with a full stop, so spacing is
      // the reliable signal there, not punctuation.
      mergeable =
        bothSingleLine ||
        continues ||
        (unfinished && fullLastLine);
    } else {
      mergeable = continues && unfinished && !shortLastLine;
    }

    if (mergeable && gap < bestGap) {
      best = group;
      bestGap = gap;
    }
  }
  return best;
}

function createGroup(block: PreparedBlock): TextGroup {
  return {
    className: block.className,
    kind: block.kind,
    text: block.text,
    lines: [...block.lines],
    rawLines: [...block.rawLines],
    left: block.left,
    right: block.right,
    top: block.top,
    bottom: block.bottom,
    width: block.width,
    height: block.height,
    lineCount: block.lineCount,
    maxLineWidth: block.maxLineWidth,
    lastLineWidth: block.lastLineWidth,
    maxLineHeight: block.maxLineHeight,
    hasGeometry: block.hasGeometry,
    allSingleLine: block.lineCount === 1,
  };
}

function mergeInto(group: TextGroup, block: PreparedBlock): void {
  group.text = joinText(group.text, block.text);
  group.lines.push(...block.lines);
  group.rawLines.push(...block.rawLines);
  group.lineCount += block.lineCount;
  group.maxLineWidth = Math.max(group.maxLineWidth, block.maxLineWidth);
  group.lastLineWidth = block.lastLineWidth;
  group.maxLineHeight = Math.max(group.maxLineHeight, block.maxLineHeight);
  group.bottom = Math.max(group.bottom, block.bottom);
  group.right = Math.max(group.right, block.right);
  group.height = group.bottom - group.top;
  group.allSingleLine = group.allSingleLine && block.lineCount === 1;
}

function compareByTopLeft(a: TextGroup, b: TextGroup): number {
  return a.top - b.top || a.left - b.left;
}

interface ColumnCluster {
  groups: TextGroup[];
  left: number;
  right: number;
}

function orderSection(section: TextGroup[], lineHeight: number): TextGroup[] {
  if (section.length <= 1) return section;
  const tolerance = Math.max(lineHeight * 1.5, 12);
  const clusters: ColumnCluster[] = [];

  for (const group of [...section].sort(compareByTopLeft)) {
    const cluster = clusters.find(
      (candidate) => Math.abs(candidate.left - group.left) <= tolerance,
    );
    if (cluster) {
      cluster.groups.push(group);
      cluster.left = Math.min(cluster.left, group.left);
      cluster.right = Math.max(cluster.right, group.right);
    } else {
      clusters.push({
        groups: [group],
        left: group.left,
        right: group.right,
      });
    }
  }

  if (clusters.length < 2) return section;
  clusters.sort((a, b) => a.left - b.left);

  // Overlapping clusters are not side-by-side columns; keep the normal
  // top-to-bottom order instead of inventing a column split.
  for (let index = 1; index < clusters.length; index += 1) {
    if (clusters[index].left < clusters[index - 1].right - tolerance) {
      return section;
    }
  }

  return clusters.flatMap((cluster) =>
    [...cluster.groups].sort(compareByTopLeft),
  );
}

/**
 * Put reconstructed groups into reading order.
 *
 * Full-width blocks, headings and verbatim blocks split the page into vertical
 * sections. Inside a section, narrow groups are grouped into columns and read
 * column by column, so two newspaper columns with several paragraphs each stay
 * "left 1, left 2, right 1, right 2" instead of interleaving by row.
 */
function orderGroups(groups: TextGroup[], metrics: PageMetrics): TextGroup[] {
  if (groups.length <= 1) return groups;
  const spanningWidth =
    metrics.bodyWidth > 0 ? metrics.bodyWidth * 0.7 : Number.POSITIVE_INFINITY;
  const pageCenter = (metrics.bodyLeft + metrics.bodyRight) / 2;
  const ordered: TextGroup[] = [];
  let section: TextGroup[] = [];

  const flush = () => {
    if (section.length > 0) {
      ordered.push(...orderSection(section, metrics.lineHeight));
      section = [];
    }
  };

  for (const group of [...groups].sort(compareByTopLeft)) {
    const centered =
      metrics.bodyWidth > 0 &&
      group.width < spanningWidth &&
      Math.abs(group.left + group.width / 2 - pageCenter) <=
        metrics.bodyWidth * 0.08;
    const spansPage =
      !group.hasGeometry ||
      group.className === "heading" ||
      group.className === "verbatim" ||
      group.width >= spanningWidth ||
      centered;
    if (spansPage) {
      flush();
      ordered.push(group);
    } else {
      section.push(group);
    }
  }
  flush();
  return ordered;
}

function textNode(text: string): JSONContent {
  return { type: "text", text };
}

function paragraphFromText(text: string): JSONContent {
  return text
    ? { type: "paragraph", content: [textNode(text)] }
    : { type: "paragraph" };
}

/**
 * Preserve the visual lines of a block whose internal line breaks carry
 * meaning (a table-like grid or an equation). Prose never takes this path.
 */
function verbatimParagraph(group: TextGroup): JSONContent {
  const content: JSONContent[] = [];
  group.rawLines.forEach((line, index) => {
    if (index > 0) content.push({ type: "hardBreak" });
    if (line) content.push(textNode(line));
  });
  return { type: "paragraph", content: content.length > 0 ? content : undefined };
}

function headingLevel(group: TextGroup, lineHeight: number): 1 | 2 | 3 {
  const ratio = group.maxLineHeight / Math.max(lineHeight, 1);
  if (ratio >= 1.35) return 1;
  if (ratio >= 1.15) return 2;
  return 3;
}

interface ParsedList {
  type: "ordered" | "bullet";
  start: number;
  items: string[];
}

const ORDERED_MARKER_RE = /^(\d{1,3})[.)]\s+(.+)$/u;
const BULLET_MARKER_RE = /^[•●▪◦‣·*\-–—]\s+(.+)$/u;

function parseListGroup(group: TextGroup): ParsedList | null {
  let type: "ordered" | "bullet" | null = null;
  let start = 1;
  const items: string[] = [];

  for (const line of group.lines) {
    const ordered = ORDERED_MARKER_RE.exec(line);
    const bullet = BULLET_MARKER_RE.exec(line);
    if (ordered) {
      if (type === "bullet") return null;
      if (type === null) {
        type = "ordered";
        start = Number.parseInt(ordered[1], 10);
      }
      items.push(ordered[2].trim());
    } else if (bullet) {
      if (type === "ordered") return null;
      type = "bullet";
      items.push(bullet[1].trim());
    } else if (items.length > 0) {
      // A wrapped line inside a list item belongs to that item.
      items[items.length - 1] = joinText(items[items.length - 1], line);
    } else {
      return null;
    }
  }

  if (type === null || items.length === 0) return null;
  return { type, start, items };
}

function listItemNode(text: string): JSONContent {
  return {
    type: "listItem",
    content: [paragraphFromText(text)],
  };
}

function buildNodes(groups: TextGroup[], lineHeight: number): JSONContent[] {
  const nodes: JSONContent[] = [];
  const listTolerance = Math.max(lineHeight * 1.5, 12);
  let openList: {
    type: "ordered" | "bullet";
    node: JSONContent;
    nextNumber: number | null;
    left: number;
  } | null = null;

  for (const group of groups) {
    if (group.className === "list") {
      const parsed = parseListGroup(group);
      if (!parsed) {
        openList = null;
        nodes.push(paragraphFromText(group.text));
        continue;
      }
      const continuesOpenList =
        openList !== null &&
        openList.type === parsed.type &&
        Math.abs(openList.left - group.left) <= listTolerance &&
        (parsed.type === "bullet" ||
          (openList.nextNumber !== null && parsed.start === openList.nextNumber));
      if (continuesOpenList && openList) {
        openList.node.content = [
          ...(openList.node.content ?? []),
          ...parsed.items.map(listItemNode),
        ];
        if (parsed.type === "ordered") {
          openList.nextNumber = parsed.start + parsed.items.length;
        }
        continue;
      }

      const node: JSONContent = {
        type: parsed.type === "ordered" ? "orderedList" : "bulletList",
        content: parsed.items.map(listItemNode),
      };
      if (parsed.type === "ordered" && parsed.start !== 1) {
        node.attrs = { start: parsed.start };
      }
      nodes.push(node);
      openList = {
        type: parsed.type,
        node,
        nextNumber:
          parsed.type === "ordered" ? parsed.start + parsed.items.length : null,
        left: group.left,
      };
      continue;
    }

    openList = null;
    if (group.className === "heading") {
      nodes.push({
        type: "heading",
        attrs: { level: headingLevel(group, lineHeight) },
        content: [textNode(group.text)],
      });
    } else if (group.className === "verbatim") {
      nodes.push(verbatimParagraph(group));
    } else {
      nodes.push(paragraphFromText(group.text));
    }
  }
  return nodes;
}

function noteNode(note: string): JSONContent {
  return {
    type: "blockquote",
    content: [{ type: "paragraph", content: [textNode(note)] }],
  };
}

/**
 * Reconstruct reviewed OCR blocks into editor content.
 *
 * The review dialog still exposes one editable block at a time; this function
 * decides what those blocks mean on the page:
 *
 * - Wrapped lines inside a block become one flowing paragraph, so Justify and
 *   normal reflow work instead of hard breaks pinning every line.
 * - Blocks that continue the same paragraph (sparse segmentation, a paragraph
 *   split across blocks, a column that continues lower on the page) are joined
 *   using geometry and text continuation.
 * - Side-by-side columns are kept apart, headings stay headings, numbered and
 *   bulleted lists become real list nodes, and table/equation blocks keep their
 *   internal line layout.
 *
 * Nothing is inferred about the text itself: only line breaks are resolved and
 * the resulting text is the reviewed text.
 */
export function ocrReconstructionContent(
  blocks: OcrReconstructionBlock[],
  note: string | null,
): JSONContent[] {
  const prepared = blocks
    .map((block, index) => prepareBlock(block, index))
    .filter((block): block is PreparedBlock => block !== null)
    .sort((a, b) => a.top - b.top || a.left - b.left || a.order - b.order);

  if (prepared.length === 0) {
    return note ? [noteNode(note)] : [];
  }

  const metrics = pageMetrics(prepared);
  const groups: TextGroup[] = [];
  for (const block of prepared) {
    block.className = classFor(block, metrics.bodyWidth);
    const target = findMergeTarget(groups, block, metrics.lineHeight);
    if (target) {
      mergeInto(target, block);
    } else {
      groups.push(createGroup(block));
    }
  }

  const nodes = buildNodes(
    orderGroups(groups, metrics),
    metrics.lineHeight,
  );
  if (note) nodes.push(noteNode(note));
  return nodes;
}
