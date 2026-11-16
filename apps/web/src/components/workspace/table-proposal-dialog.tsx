import { CircleAlert, Table2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type { OcrBlock, PageSummary, TableProposalCell } from "@docurebuild/shared-types";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Spinner } from "@/components/ui/spinner";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useTableProposal } from "@/hooks/use-table-proposal";
import { cn } from "@/lib/utils";
import { useWorkspaceActions } from "./workspace-actions-context";

interface TableProposalDialogProps {
  projectId: string;
  page: PageSummary | null;
  block: OcrBlock | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInserted?: () => void;
}

/**
 * Shows the proposed grid exactly as it will be inserted. The user can choose a
 * header row and must acknowledge flagged cells before the insert button becomes
 * available. Nothing is saved by opening this dialog.
 */
export function TableProposalDialog({
  projectId,
  page,
  block,
  open,
  onOpenChange,
  onInserted,
}: TableProposalDialogProps) {
  const { t } = useTranslation("workspace");
  const errorMessage = useApiErrorMessage();
  const { insertTable } = useWorkspaceActions();

  const proposalQuery = useTableProposal(
    projectId,
    page?.id ?? null,
    block?.id ?? null,
    open,
  );
  const proposal = proposalQuery.data ?? null;

  const [headerRow, setHeaderRow] = useState(false);
  const [includeNote, setIncludeNote] = useState(true);
  const [acknowledged, setAcknowledged] = useState(false);

  useEffect(() => {
    if (!open) return;
    setHeaderRow(false);
    setIncludeNote(true);
    setAcknowledged(false);
  }, [open, block?.id]);

  const matrix = useMemo(() => {
    if (!proposal) return [] as (TableProposalCell | null)[][];
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

  const needsReview = Boolean(
    proposal &&
      (proposal.uncertain_cells > 0 || proposal.warnings.includes("no_confidence")),
  );
  const canInsert = Boolean(proposal) && (!needsReview || acknowledged);

  const handleInsert = () => {
    if (!proposal || !canInsert) return;
    insertTable({
      rows: matrix.map((row) => row.map((cell) => cell?.text ?? "")),
      headerRow,
      note: includeNote
        ? t("ocr.table.sourceNote", { page: page?.page_number ?? "—" })
        : null,
    });
    toast.success(t("ocr.table.inserted"));
    onOpenChange(false);
    onInserted?.();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] max-w-4xl flex-col gap-4 overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Table2 className="size-icon-sm text-primary" aria-hidden="true" />
            {t("ocr.table.title", { page: page?.page_number ?? "—" })}
          </DialogTitle>
          <DialogDescription>{t("ocr.table.description")}</DialogDescription>
        </DialogHeader>

        {proposalQuery.isLoading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-xs text-muted-foreground">
            <Spinner className="size-icon-lg text-primary" />
            <span>{t("ocr.table.loading")}</span>
          </div>
        ) : proposalQuery.isError ? (
          <EmptyState
            compact
            icon={CircleAlert}
            title={t("ocr.table.errorTitle")}
            description={errorMessage(proposalQuery.error)}
            action={
              <Button
                variant="outline"
                size="sm"
                onClick={() => void proposalQuery.refetch()}
              >
                {t("ocr.table.retry")}
              </Button>
            }
          />
        ) : proposal ? (
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

            <div className="scrollbar-thin min-h-0 flex-1 overflow-auto rounded-lg border border-border/70 bg-background/40">
              <table className="w-full border-collapse text-xs">
                <tbody>
                  {matrix.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {row.map((cell, columnIndex) => {
                        const isHeader = headerRow && rowIndex === 0;
                        const confidence =
                          cell?.confidence === null || cell?.confidence === undefined
                            ? null
                            : Math.round(cell.confidence);
                        const title = cell?.uncertain
                          ? t("ocr.table.uncertainCell")
                          : confidence !== null
                            ? t("ocr.table.confidence", { value: confidence })
                            : undefined;
                        const className = cn(
                          "min-w-20 border border-border/60 px-2 py-1.5 align-top font-document leading-relaxed",
                          isHeader && "bg-muted/40 font-semibold",
                          cell?.uncertain && "bg-warning/10",
                          cell?.empty && "bg-muted/20",
                        );
                        const content = (
                          <span className="flex items-start gap-1">
                            {cell?.uncertain ? (
                              <CircleAlert
                                className="mt-0.5 size-3 shrink-0 text-warning"
                                aria-hidden="true"
                              />
                            ) : null}
                            {cell?.text ? (
                              <span className="whitespace-pre-wrap break-words">
                                {cell.text}
                              </span>
                            ) : (
                              <span className="sr-only">{t("ocr.table.emptyCell")}</span>
                            )}
                          </span>
                        );
                        return isHeader ? (
                          <th
                            key={columnIndex}
                            scope="col"
                            title={title}
                            className={className}
                          >
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

            <div className="space-y-2 rounded-lg border border-border/60 bg-background/45 p-3">
              <label className="flex items-center gap-2 text-2xs text-muted-foreground">
                <input
                  type="checkbox"
                  className="size-3.5 accent-primary"
                  checked={headerRow}
                  onChange={(event) => setHeaderRow(event.target.checked)}
                />
                {t("ocr.table.headerRow")}
              </label>
              {needsReview ? (
                <label className="flex items-start gap-2 text-2xs text-muted-foreground">
                  <input
                    type="checkbox"
                    className="mt-0.5 size-3.5 accent-primary"
                    checked={acknowledged}
                    onChange={(event) => setAcknowledged(event.target.checked)}
                  />
                  {t("ocr.table.acknowledge")}
                </label>
              ) : null}
            </div>
          </>
        ) : null}

        <DialogFooter className="mt-0 shrink-0 items-stretch gap-2 border-t border-border/60 pt-3 sm:items-center">
          <label className="mr-auto flex items-center gap-1.5 text-2xs text-muted-foreground">
            <input
              type="checkbox"
              className="size-3.5 accent-primary"
              checked={includeNote}
              onChange={(event) => setIncludeNote(event.target.checked)}
              disabled={!proposal}
            />
            {t("ocr.table.includeNote")}
          </label>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("ocr.table.dismiss")}
          </Button>
          <Button
            className="gap-1.5"
            onClick={handleInsert}
            disabled={!canInsert || proposalQuery.isFetching}
          >
            <Table2 />
            {t("ocr.table.insert")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
