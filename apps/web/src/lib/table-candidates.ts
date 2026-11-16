import type {
  TableProposalCandidate,
  TableProposalCell,
  TableProposalWarning,
} from "@docurebuild/shared-types";

/** Fields shared by a single-block proposal and a page-level candidate. */
export interface TableGridProposal {
  rows: number;
  columns: number;
  uncertain_cells: number;
  empty_cells: number;
  warnings: TableProposalWarning[];
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
