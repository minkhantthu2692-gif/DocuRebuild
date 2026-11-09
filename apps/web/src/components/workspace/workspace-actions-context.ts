import { createContext, useContext } from "react";

export interface WorkspaceInsertion {
  id: number;
  text: string;
  note: string | null;
}

export interface WorkspaceActions {
  insertion: WorkspaceInsertion | null;
  insertText: (text: string, note?: string | null) => void;
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
