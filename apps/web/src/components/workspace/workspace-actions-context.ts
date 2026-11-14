import { createContext, useContext } from "react";

import type { DocumentRecord } from "@docurebuild/shared-types";

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

export type WorkspaceInsertion = WorkspaceTextInsertion | WorkspaceFigureInsertion;

export type FigureInsertionInput = Omit<WorkspaceFigureInsertion, "id" | "type">;

export interface WorkspaceActions {
  insertion: WorkspaceInsertion | null;
  insertText: (text: string, note?: string | null) => void;
  insertFigure: (figure: FigureInsertionInput) => void;
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
