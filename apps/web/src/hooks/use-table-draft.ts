import { useCallback, useMemo, useState } from "react";

import {
  proposalRows,
  type TableGridProposal,
} from "@/lib/table-candidates";

export interface TableDraft {
  /** Cell matrix to insert, with any manual edits applied. */
  rows: string[][];
  /** Coordinates (`row:column`) whose text differs from the proposal. */
  edited: ReadonlySet<string>;
  changedCount: number;
  setCell: (row: number, column: number, text: string) => void;
  reset: () => void;
}

interface DraftState {
  key: string;
  edits: Record<string, string>;
}

const EMPTY_STATE: DraftState = { key: "", edits: {} };

/**
 * Manual corrections for a reviewed table. The proposal stays untouched: edits
 * live beside it and are only written into the document when the user inserts
 * the table. A different proposal (another block or candidate) starts clean.
 */
export function useTableDraft(
  proposal: TableGridProposal | null,
  key: string,
): TableDraft {
  const [state, setState] = useState<DraftState>(EMPTY_STATE);

  const originals = useMemo(() => {
    const map = new Map<string, string>();
    for (const cell of proposal?.cells ?? []) {
      map.set(`${cell.row}:${cell.column}`, cell.text);
    }
    return map;
  }, [proposal]);

  const { rows, edited } = useMemo(() => {
    if (!proposal) {
      return { rows: [] as string[][], edited: new Set<string>() };
    }
    const matrix = proposalRows(proposal);
    const changed = new Set<string>();
    if (state.key !== key) {
      return { rows: matrix, edited: changed };
    }
    for (const [coordinate, text] of Object.entries(state.edits)) {
      const [row, column] = coordinate.split(":").map(Number);
      if (matrix[row]?.[column] === undefined) continue;
      // An edit that matches the proposal again is not a change, even if it was
      // recorded before the proposal was refetched.
      if (text === (originals.get(coordinate) ?? "")) continue;
      matrix[row][column] = text;
      changed.add(coordinate);
    }
    return { rows: matrix, edited: changed };
  }, [proposal, key, state.key, state.edits, originals]);

  const setCell = useCallback(
    (row: number, column: number, text: string) => {
      const coordinate = `${row}:${column}`;
      setState((previous) => {
        const base = previous.key === key ? previous.edits : {};
        const next = { ...base };
        if (text === (originals.get(coordinate) ?? "")) {
          delete next[coordinate];
        } else {
          next[coordinate] = text;
        }
        return { key, edits: next };
      });
    },
    [key, originals],
  );

  const reset = useCallback(() => setState({ key, edits: {} }), [key]);

  return {
    rows,
    edited,
    changedCount: edited.size,
    setCell,
    reset,
  };
}
