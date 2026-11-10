import { createContext, useContext } from "react";

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
}

export const WorkspaceActionsContext = createContext<WorkspaceActions | null>(null);

export function useWorkspaceActions(): WorkspaceActions {
  const context = useContext(WorkspaceActionsContext);
  if (!context) {
    throw new Error("useWorkspaceActions must be used inside WorkspaceActionsProvider");
  }
  return context;
}
