import { createContext, useContext } from "react";

import type {
  DocumentRecord,
  TableAlignment,
} from "@docurebuild/shared-types";

import type { OcrReconstructionBlock } from "@/lib/ocr-reconstruction";

export interface WorkspaceTextInsertion {
  id: number;
  type: "text";
  text: string;
  note: string | null;
  /**
   * Reviewed OCR blocks with their source geometry. When present the editor
   * reconstructs paragraphs from the layout instead of splitting on blank
   * lines; plain extracted text keeps the older text-only behaviour.
   */
  blocks?: OcrReconstructionBlock[];
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

export interface WorkspaceInlineImageInsertion {
  id: number;
  type: "inlineImage";
  src: string;
  alt: string;
}

export interface WorkspaceTableInsertion {
  id: number;
  type: "table";
  /** Final reviewed cell text. Empty strings stay empty. */
  rows: string[][];
  /** Per-cell alignment observed in the source; null keeps the default. */
  alignments: (TableAlignment | null)[][];
  /** Merged-cell row spans; 0 marks a coordinate covered by another cell. */
  rowSpans: number[][];
  /** Merged-cell column spans; 0 marks a covered coordinate. */
  colSpans: number[][];
  headerRow: boolean;
  note: string | null;
}

export interface WorkspaceEquationInsertion {
  id: number;
  type: "equation";
  /** Reviewed LaTeX source, never generated text. */
  latex: string;
  numbered: boolean;
  note: string | null;
}

export type WorkspaceInsertion =
  | WorkspaceTextInsertion
  | WorkspaceFigureInsertion
  | WorkspaceInlineImageInsertion
  | WorkspaceTableInsertion
  | WorkspaceEquationInsertion;

export type FigureInsertionInput = Omit<WorkspaceFigureInsertion, "id" | "type">;
export type InlineImageInsertionInput = Omit<
  WorkspaceInlineImageInsertion,
  "id" | "type"
>;
export type TableInsertionInput = Omit<WorkspaceTableInsertion, "id" | "type">;
export type EquationInsertionInput = Omit<WorkspaceEquationInsertion, "id" | "type">;

export interface WorkspaceActions {
  insertion: WorkspaceInsertion | null;
  insertText: (
    text: string,
    note?: string | null,
    blocks?: OcrReconstructionBlock[],
  ) => void;
  insertFigure: (figure: FigureInsertionInput) => void;
  insertInlineImage: (image: InlineImageInsertionInput) => void;
  insertTable: (table: TableInsertionInput) => void;
  insertEquation: (equation: EquationInsertionInput) => void;
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
