import { ChevronRight, CircleAlert, Table2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type { PageSummary } from "@docurebuild/shared-types";

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
import { useTableDraft } from "@/hooks/use-table-draft";
import { usePageTableProposals } from "@/hooks/use-table-proposal";
import { api } from "@/lib/api";
import {
  needsTableAcknowledgement,
  proposalAlignments,
  tableCandidatePreview,
} from "@/lib/table-candidates";
import { TableReview } from "./table-review";
import { useWorkspaceActions } from "./workspace-actions-context";

interface PageTablesDialogProps {
  projectId: string;
  page: PageSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInserted?: () => void;
}

/**
 * Lists the tables the backend can build from this page's stored word boxes.
 * A candidate may span several blocks, which is how embedded PDF text becomes a
 * table. Selecting one shows the same review grid as a single-block proposal,
 * and nothing is inserted without confirmation.
 */
export function PageTablesDialog({
  projectId,
  page,
  open,
  onOpenChange,
  onInserted,
}: PageTablesDialogProps) {
  const { t } = useTranslation("workspace");
  const errorMessage = useApiErrorMessage();
  const { insertTable } = useWorkspaceActions();

  const proposalsQuery = usePageTableProposals(projectId, page?.id ?? null, open);
  const candidates = proposalsQuery.data?.candidates ?? [];

  const [selected, setSelected] = useState<number | null>(null);
  const [headerRow, setHeaderRow] = useState(false);
  const [includeNote, setIncludeNote] = useState(true);
  const [acknowledged, setAcknowledged] = useState(false);

  const candidate = selected !== null ? (candidates[selected] ?? null) : null;
  const draft = useTableDraft(candidate, candidate?.block_ids.join("|") ?? "");
  const resetDraft = draft.reset;

  useEffect(() => {
    if (!open) {
      setSelected(null);
      return;
    }
    setHeaderRow(false);
    setIncludeNote(true);
    setAcknowledged(false);
    resetDraft();
  }, [open, resetDraft]);

  useEffect(() => {
    setHeaderRow(false);
    setAcknowledged(false);
  }, [selected]);

  const needsReview = candidate ? needsTableAcknowledgement(candidate) : false;
  const canInsert = Boolean(candidate) && (!needsReview || acknowledged);
  const sourceImageUrl = page
    ? api.assetUrl(
        projectId,
        page.display_asset_id ?? page.original_asset_id,
        page.updated_at,
      )
    : null;

  const handleInsert = () => {
    if (!candidate || !canInsert) return;
    insertTable({
      rows: draft.rows,
      alignments: proposalAlignments(candidate),
      headerRow,
      note: includeNote
        ? t("ocr.table.sourceNotePage", { page: page?.page_number ?? "—" })
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
            {t("ocr.table.detectTitle", { page: page?.page_number ?? "—" })}
          </DialogTitle>
          <DialogDescription>{t("ocr.table.detectDescription")}</DialogDescription>
        </DialogHeader>

        {proposalsQuery.isLoading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-xs text-muted-foreground">
            <Spinner className="size-icon-lg text-primary" />
            <span>{t("ocr.table.loading")}</span>
          </div>
        ) : proposalsQuery.isError ? (
          <EmptyState
            compact
            icon={CircleAlert}
            title={t("ocr.table.errorTitle")}
            description={errorMessage(proposalsQuery.error)}
            action={
              <Button
                variant="outline"
                size="sm"
                onClick={() => void proposalsQuery.refetch()}
              >
                {t("ocr.table.retry")}
              </Button>
            }
          />
        ) : candidate ? (
          <TableReview
            proposal={candidate}
            draft={draft}
            sourceImageUrl={sourceImageUrl}
            pageWidth={proposalsQuery.data?.page_width}
            pageHeight={proposalsQuery.data?.page_height}
            headerRow={headerRow}
            onHeaderRowChange={setHeaderRow}
            acknowledged={acknowledged}
            onAcknowledgedChange={setAcknowledged}
          />
        ) : candidates.length === 0 ? (
          <EmptyState
            compact
            icon={Table2}
            title={t("ocr.table.detectEmptyTitle")}
            description={t("ocr.table.detectEmptyDescription")}
          />
        ) : (
          <>
            <p className="text-2xs text-muted-foreground">
              {t("ocr.table.detectCount", { count: candidates.length })}
            </p>
            <ul className="scrollbar-thin min-h-0 flex-1 space-y-2 overflow-auto">
              {candidates.map((item, index) => {
                const preview = tableCandidatePreview(item);
                return (
                  <li key={item.block_ids.join(":")}>
                    <button
                      type="button"
                      className="flex w-full items-center gap-3 rounded-lg border border-border/70 bg-background/50 p-3 text-left transition-colors hover:border-primary/40 hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      onClick={() => setSelected(index)}
                    >
                      <Table2
                        className="size-icon-sm shrink-0 text-primary"
                        aria-hidden="true"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="flex flex-wrap items-center gap-1.5">
                          <span className="text-xs font-medium">
                            {t("ocr.table.rowsColumns", {
                              rows: item.rows,
                              columns: item.columns,
                            })}
                          </span>
                          {item.uncertain_cells > 0 ? (
                            <Badge variant="warning">
                              {t("ocr.table.uncertain", {
                                count: item.uncertain_cells,
                              })}
                            </Badge>
                          ) : null}
                          {item.block_ids.length > 1 ? (
                            <Badge variant="outline">
                              {t("ocr.table.blockCount", {
                                count: item.block_ids.length,
                              })}
                            </Badge>
                          ) : null}
                        </span>
                        {preview ? (
                          <span className="mt-1 block truncate text-2xs text-muted-foreground">
                            {preview}
                          </span>
                        ) : null}
                      </span>
                      <ChevronRight
                        className="size-icon-sm shrink-0 text-muted-foreground"
                        aria-hidden="true"
                      />
                    </button>
                  </li>
                );
              })}
            </ul>
          </>
        )}

        <DialogFooter className="mt-0 shrink-0 items-stretch gap-2 border-t border-border/60 pt-3 sm:items-center">
          {candidate ? (
            <div className="mr-auto flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-1.5 text-2xs text-muted-foreground">
                <input
                  type="checkbox"
                  className="size-3.5 accent-primary"
                  checked={includeNote}
                  onChange={(event) => setIncludeNote(event.target.checked)}
                />
                {t("ocr.table.includeNote")}
              </label>
              <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>
                {t("ocr.table.back")}
              </Button>
            </div>
          ) : null}
          <Button
            variant="outline"
            className={candidate ? undefined : "ml-auto"}
            onClick={() => onOpenChange(false)}
          >
            {t("ocr.table.dismiss")}
          </Button>
          {candidate ? (
            <Button
              className="gap-1.5"
              onClick={handleInsert}
              disabled={!canInsert || proposalsQuery.isFetching}
            >
              <Table2 />
              {t("ocr.table.insert")}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
