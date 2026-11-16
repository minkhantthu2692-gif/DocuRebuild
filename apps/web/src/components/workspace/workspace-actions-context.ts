import { createContext, useContext } from "react";

import type {
  DocumentRecord,
  TableAlignment,
} from "@docurebuild/shared-types";

export interface WorkspaceTextInsertion {
  id: number;
  type: "text";
  text: string;
  note: string | null;
}

export interface WorkspaceFigureInsertion {
  id: number;
  type: "figure";
  src: string;
  alt: string;
  caption: string;
  note: string | null;
  width: number | null;
  height: number | null;
}

export interface WorkspaceTableInsertion {
  id: number;
  type: "table";
  /** Final reviewed cell text. Empty strings stay empty. */
  rows: string[][];
  /** Per-cell alignment observed in the source; null keeps the default. */
  alignments: (TableAlignment | null)[][];
  headerRow: boolean;
  note: string | null;
}

export type WorkspaceInsertion =
  | WorkspaceTextInsertion
  | WorkspaceFigureInsertion
  | WorkspaceTableInsertion;

export type FigureInsertionInput = Omit<WorkspaceFigureInsertion, "id" | "type">;
export type TableInsertionInput = Omit<WorkspaceTableInsertion, "id" | "type">;

export interface WorkspaceActions {
  insertion: WorkspaceInsertion | null;
  insertText: (text: string, note?: string | null) => void;
  insertFigure: (figure: FigureInsertionInput) => void;
  insertTable: (table: TableInsertionInput) => void;
  consumeInsertion: (id: number) => void;
  /**
   * A document restored from a backup, waiting for the editor to apply it.
   * The editor owns its working copy, so a query refetch alone would not update
   * the visible text.
   */
  pendingDocumentRestore: DocumentRecord | null;
  restoreDocumentIntoEditor: (record: DocumentRecord) => void;
  consumeDocumentRestore: () => void;
}

export const WorkspaceActionsContext = createContext<WorkspaceActions | null>(null);

export function useWorkspaceActions(): WorkspaceActions {
  const context = useContext(WorkspaceActionsContext);
  if (!context) {
    throw new Error("useWorkspaceActions must be used inside WorkspaceActionsProvider");
  }
  return context;
}
