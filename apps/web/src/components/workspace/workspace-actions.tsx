import { useCallback, useMemo, useState, type ReactNode } from "react";

import type { DocumentRecord } from "@docurebuild/shared-types";

import {
  WorkspaceActionsContext,
  type FigureInsertionInput,
  type WorkspaceInsertion,
} from "./workspace-actions-context";

let nextInsertionId = 1;

export function WorkspaceActionsProvider({ children }: { children: ReactNode }) {
  const [insertion, setInsertion] = useState<WorkspaceInsertion | null>(null);
  const [pendingDocumentRestore, setPendingDocumentRestore] =
    useState<DocumentRecord | null>(null);

  const insertText = useCallback((text: string, note?: string | null) => {
    setInsertion({ id: nextInsertionId++, type: "text", text, note: note ?? null });
  }, []);

  const insertFigure = useCallback((figure: FigureInsertionInput) => {
    setInsertion({ id: nextInsertionId++, type: "figure", ...figure });
  }, []);

  const consumeInsertion = useCallback((id: number) => {
    setInsertion((current) => (current?.id === id ? null : current));
  }, []);

  const restoreDocumentIntoEditor = useCallback((record: DocumentRecord) => {
    setPendingDocumentRestore(record);
  }, []);

  const consumeDocumentRestore = useCallback(() => {
    setPendingDocumentRestore(null);
  }, []);

  const value = useMemo(
    () => ({
      insertion,
      insertText,
      insertFigure,
      consumeInsertion,
      pendingDocumentRestore,
      restoreDocumentIntoEditor,
      consumeDocumentRestore,
    }),
    [
      insertion,
      insertText,
      insertFigure,
      consumeInsertion,
      pendingDocumentRestore,
      restoreDocumentIntoEditor,
      consumeDocumentRestore,
    ],
  );

  return (
    <WorkspaceActionsContext.Provider value={value}>
      {children}
    </WorkspaceActionsContext.Provider>
  );
}
