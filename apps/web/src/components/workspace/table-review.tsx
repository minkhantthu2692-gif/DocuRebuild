import { CircleAlert, PencilLine, ScanEye, Undo2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import type { TableProposalCell } from "@docurebuild/shared-types";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { TableDraft } from "@/hooks/use-table-draft";
import {
  needsTableAcknowledgement,
  sourceCropGeometry,
  type TableGridProposal,
} from "@/lib/table-candidates";
import { cn } from "@/lib/utils";
import { TableSourcePreview } from "./table-source-preview";

/**
 * The reviewable part of a table proposal. Both the single-block dialog and the
 * page-level candidate dialog show exactly this grid, so a cell is never
 * presented differently depending on where the proposal came from.
 */
interface TableReviewProps {
  proposal: TableGridProposal;
  /** Manual corrections that will be inserted instead of the raw proposal. */
  draft: TableDraft;
  /** Page image the proposal was read from, when one is available. */
  sourceImageUrl?: string | null;
  pageWidth?: number | null;
  pageHeight?: number | null;
  headerRow: boolean;
  onHeaderRowChange: (checked: boolean) => void;
  acknowledged: boolean;
  onAcknowledgedChange: (checked: boolean) => void;
}

export function TableReview({
  proposal,
  draft,
  sourceImageUrl,
  pageWidth = null,
  pageHeight = null,
  headerRow,
  onHeaderRowChange,
  acknowledged,
  onAcknowledgedChange,
}: TableReviewProps) {
  const { t } = useTranslation("workspace");
  const needsReview = needsTableAcknowledgement(proposal);
  const [showSource, setShowSource] = useState(true);
  const [editing, setEditing] = useState(false);
  const canShowSource =
    Boolean(sourceImageUrl) &&
    sourceCropGeometry(proposal.source, pageWidth, pageHeight) !== null;

  const matrix = useMemo(() => {
    const rows = Array.from({ length: proposal.rows }, () =>
      Array.from({ length: proposal.columns }, () => null as TableProposalCell | null),
    );
    for (const cell of proposal.cells) {
      if (rows[cell.row]?.[cell.column] !== undefined) {
        rows[cell.row][cell.column] = cell;
      }
    }
    return rows;
  }, [proposal]);

  return (
    <>
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="outline">
          {t("ocr.table.rowsColumns", {
            rows: proposal.rows,
            columns: proposal.columns,
          })}
        </Badge>
        {proposal.uncertain_cells > 0 ? (
          <Badge variant="warning">
            {t("ocr.table.uncertain", { count: proposal.uncertain_cells })}
          </Badge>
        ) : null}
        {proposal.empty_cells > 0 ? (
          <Badge variant="outline">
            {t("ocr.table.empty", { count: proposal.empty_cells })}
          </Badge>
        ) : null}
        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          {draft.changedCount > 0 ? (
            <Badge variant="secondary">
              {t("ocr.table.editedCells", { count: draft.changedCount })}
            </Badge>
          ) : null}
          {draft.changedCount > 0 ? (
            <Button
              variant="ghost"
              size="sm"
              className="gap-1.5"
              onClick={draft.reset}
            >
              <Undo2 />
              {t("ocr.table.resetCells")}
            </Button>
          ) : null}
          <Button
            variant={editing ? "secondary" : "ghost"}
            size="sm"
            className="gap-1.5"
            aria-pressed={editing}
            onClick={() => setEditing((current) => !current)}
          >
            <PencilLine />
            {editing ? t("ocr.table.finishEditing") : t("ocr.table.editCells")}
          </Button>
          {canShowSource ? (
            <Button
              variant="ghost"
              size="sm"
              className="gap-1.5"
              onClick={() => setShowSource((current) => !current)}
            >
              <ScanEye />
              {showSource ? t("ocr.table.hideSource") : t("ocr.table.compareSource")}
            </Button>
          ) : null}
        </div>
      </div>

      {proposal.warnings.includes("no_confidence") ? (
        <p className="flex gap-2 rounded-lg border border-border/60 bg-background/50 p-3 text-2xs leading-relaxed text-muted-foreground">
          <CircleAlert
            className="mt-0.5 size-icon-sm shrink-0 text-warning"
            aria-hidden="true"
          />
          <span>{t("ocr.table.noConfidence")}</span>
        </p>
      ) : proposal.uncertain_cells > 0 ? (
        <p className="flex gap-2 rounded-lg border border-warning/40 bg-warning/10 p-3 text-2xs leading-relaxed text-muted-foreground">
          <CircleAlert
            className="mt-0.5 size-icon-sm shrink-0 text-warning"
            aria-hidden="true"
          />
          <span>{t("ocr.table.lowConfidence")}</span>
        </p>
      ) : null}

      {editing ? (
        <p className="text-2xs leading-relaxed text-muted-foreground">
          {t("ocr.table.editHint")}
        </p>
      ) : null}

      <div
        className={cn(
          "grid min-h-0 flex-1 gap-3",
          canShowSource && showSource && sourceImageUrl && "md:grid-cols-2",
        )}
      >
        {canShowSource && showSource && sourceImageUrl ? (
          <div className="scrollbar-thin min-h-0 overflow-auto">
            <TableSourcePreview
              proposal={proposal}
              pageWidth={pageWidth}
              pageHeight={pageHeight}
              imageUrl={sourceImageUrl}
            />
          </div>
        ) : null}

        <div className="scrollbar-thin min-h-0 overflow-auto rounded-lg border border-border/70 bg-background/40">
          <table className="w-full border-collapse text-xs">
            <tbody>
              {matrix.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, columnIndex) => {
                    const coordinate = `${rowIndex}:${columnIndex}`;
                    const isHeader = headerRow && rowIndex === 0;
                    const isEdited = draft.edited.has(coordinate);
                    const value = draft.rows[rowIndex]?.[columnIndex] ?? "";
                    const alignment = cell?.alignment ?? null;
                    const confidence =
                      cell?.confidence === null || cell?.confidence === undefined
                        ? null
                        : Math.round(cell.confidence);
                    const title = isEdited
                      ? t("ocr.table.editedCell")
                      : cell?.uncertain
                        ? t("ocr.table.uncertainCell")
                        : confidence !== null
                          ? t("ocr.table.confidence", { value: confidence })
                          : undefined;
                    const className = cn(
                      "min-w-20 border border-border/60 px-2 py-1.5 align-top font-document leading-relaxed",
                      isHeader && "bg-muted/40 font-semibold",
                      cell?.uncertain && !isEdited && "bg-warning/10",
                      cell?.empty && !value && "bg-muted/20",
                      isEdited && "bg-primary/5 ring-1 ring-inset ring-primary/30",
                    );
                    const content = editing ? (
                      <textarea
                        value={value}
                        rows={Math.min(Math.max(value.split("\n").length, 1), 6)}
                        aria-label={t("ocr.table.cellLabel", {
                          row: rowIndex + 1,
                          column: columnIndex + 1,
                        })}
                        onChange={(event) =>
                          draft.setCell(rowIndex, columnIndex, event.target.value)
                        }
                        style={alignment ? { textAlign: alignment } : undefined}
                        className={cn(
                          "block w-full resize-y bg-transparent p-0 text-xs leading-relaxed outline-none focus-visible:ring-1 focus-visible:ring-ring",
                          isHeader && "font-semibold",
                        )}
                      />
                    ) : (
                      <span
                        className="block whitespace-pre-wrap break-words"
                        style={alignment ? { textAlign: alignment } : undefined}
                      >
                        {cell?.uncertain ? (
                          <CircleAlert
                            className="mr-1 inline-block size-3 align-text-top text-warning"
                            aria-hidden="true"
                          />
                        ) : null}
                        {value || (
                          <span className="sr-only">{t("ocr.table.emptyCell")}</span>
                        )}
                      </span>
                    );
                    return isHeader ? (
                      <th key={columnIndex} scope="col" title={title} className={className}>
                        {content}
                      </th>
                    ) : (
                      <td key={columnIndex} title={title} className={className}>
                        {content}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="space-y-2 rounded-lg border border-border/60 bg-background/45 p-3">
        <label className="flex items-center gap-2 text-2xs text-muted-foreground">
          <input
            type="checkbox"
            className="size-3.5 accent-primary"
            checked={headerRow}
            onChange={(event) => onHeaderRowChange(event.target.checked)}
          />
          {t("ocr.table.headerRow")}
        </label>
        {needsReview ? (
          <label className="flex items-start gap-2 text-2xs text-muted-foreground">
            <input
              type="checkbox"
              className="mt-0.5 size-3.5 accent-primary"
              checked={acknowledged}
              onChange={(event) => onAcknowledgedChange(event.target.checked)}
            />
            {t("ocr.table.acknowledge")}
          </label>
        ) : null}
      </div>
    </>
  );
}
