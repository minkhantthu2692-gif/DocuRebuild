import type {
  TableAlignment,
  TableProposalCandidate,
  TableProposalCell,
  TableProposalWarning,
  TableSourceBox,
} from "@docurebuild/shared-types";

/** Fields shared by a single-block proposal and a page-level candidate. */
export interface TableGridProposal {
  rows: number;
  columns: number;
  uncertain_cells: number;
  empty_cells: number;
  warnings: TableProposalWarning[];
  source: TableSourceBox;
  cells: TableProposalCell[];
}

/** A flagged or unscored cell must be acknowledged before insertion. */
export function needsTableAcknowledgement(proposal: TableGridProposal): boolean {
  return proposal.uncertain_cells > 0 || proposal.warnings.includes("no_confidence");
}

/**
 * Turn sparse cell coordinates into the rectangular text matrix the editor
 * expects. Missing coordinates stay empty instead of being guessed.
 */
export function proposalRows(
  proposal: Pick<TableGridProposal, "rows" | "columns" | "cells">,
): string[][] {
  const rows = Array.from({ length: proposal.rows }, () =>
    Array.from({ length: proposal.columns }, () => ""),
  );
  for (const cell of proposal.cells) {
    if (rows[cell.row]?.[cell.column] !== undefined) {
      rows[cell.row][cell.column] = cell.text;
    }
  }
  return rows;
}

/** One-line preview of a candidate, built from its first visual row. */
export function tableCandidatePreview(candidate: TableProposalCandidate): string {
  return candidate.cells
    .filter((cell) => cell.row === 0)
    .sort((left, right) => left.column - right.column)
    .map((cell) => cell.text.trim())
    .filter(Boolean)
    .join(" · ");
}

/**
 * Alignment matrix in the same shape as `proposalRows`. A coordinate the
 * proposal does not include keeps `null`, so insertion does not apply an
 * alignment the backend never observed.
 */
export function proposalAlignments(
  proposal: Pick<TableGridProposal, "rows" | "columns" | "cells">,
): (TableAlignment | null)[][] {
  const grid = Array.from({ length: proposal.rows }, () =>
    Array.from({ length: proposal.columns }, () => null as TableAlignment | null),
  );
  for (const cell of proposal.cells) {
    if (grid[cell.row]?.[cell.column] !== undefined) {
      grid[cell.row][cell.column] = cell.alignment;
    }
  }
  return grid;
}

/** Positioning for a crop preview, as percentages of the preview box. */
export interface SourceCropGeometry {
  /** Width divided by height of the visible crop. */
  aspectRatio: number;
  image: {
    left: number;
    top: number;
    width: number;
    height: number;
  };
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}

/**
 * Map the proposal's source box onto the whole page image so it can be shown as
 * a crop. A box outside the page is clamped rather than scaled, and an unusable
 * box returns null instead of an empty preview.
 */
export function sourceCropGeometry(
  box: TableSourceBox,
  pageWidth: number | null,
  pageHeight: number | null,
): SourceCropGeometry | null {
  if (
    !pageWidth ||
    !pageHeight ||
    pageWidth <= 0 ||
    pageHeight <= 0 ||
    box.width <= 0 ||
    box.height <= 0
  ) {
    return null;
  }
  const left = clamp(box.x, 0, pageWidth);
  const top = clamp(box.y, 0, pageHeight);
  const right = clamp(box.x + box.width, 0, pageWidth);
  const bottom = clamp(box.y + box.height, 0, pageHeight);
  const width = right - left;
  const height = bottom - top;
  if (width <= 0 || height <= 0) {
    return null;
  }
  return {
    aspectRatio: width / height,
    image: {
      // `0 - value` avoids a negative zero when the crop starts at the edge.
      left: 0 - (left / width) * 100,
      top: 0 - (top / height) * 100,
      width: (pageWidth / width) * 100,
      height: (pageHeight / height) * 100,
    },
  };
}
