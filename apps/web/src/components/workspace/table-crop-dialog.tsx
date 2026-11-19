import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, ScanText, Sparkles, Table2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type {
  AiTableResponse,
  ElementSummary,
  ElementTableResponse,
  PageSummary,
} from "@docurebuild/shared-types";

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
import { Spinner } from "@/components/ui/spinner";
import { useAiTasks } from "@/hooks/use-ai";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useOcrCapabilities } from "@/hooks/use-ocr";
import { useTableDraft } from "@/hooks/use-table-draft";
import { api } from "@/lib/api";
import {
  needsTableAcknowledgement,
  proposalAlignments,
  proposalSpans,
} from "@/lib/table-candidates";
import { usePaidAiGuard } from "./paid-ai-confirm-dialog";
import { TableReview } from "./table-review";
import { useWorkspaceActions } from "./workspace-actions-context";

interface TableCropDialogProps {
  projectId: string;
  /** The saved table region whose crop is read. */
  element: ElementSummary | null;
  page: PageSummary | null;
  /** Languages for the local OCR engine. Empty means the application default. */
  languages: string[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInserted?: () => void;
}

type CropProposal =
  | { kind: "local"; grid: ElementTableResponse }
  | { kind: "ai"; grid: AiTableResponse };

/**
 * Reads one saved table crop into the normal table review grid.
 *
 * Local OCR runs on this device and is offered first; the vision model is an
 * optional second method for crops the engine reads poorly. Both produce a
 * proposal only: nothing is written to the element or the document, insertion
 * stays disabled until the user acknowledges the grid, and manual cell
 * corrections are inserted instead of the raw result.
 */
export function TableCropDialog({
  projectId,
  element,
  page,
  languages,
  open,
  onOpenChange,
  onInserted,
}: TableCropDialogProps) {
  const { t } = useTranslation("workspace");
  const { t: tCommon } = useTranslation("common");
  const { insertTable } = useWorkspaceActions();
  const errorMessage = useApiErrorMessage();
  const queryClient = useQueryClient();
  const capabilities = useOcrCapabilities();
  const ocrAvailable = Boolean(capabilities.data?.available);
  const tasksQuery = useAiTasks();
  const tableTask = tasksQuery.data?.tasks.table_structure;
  const visionModel = tableTask?.model_id ?? "";
  const paidAi = usePaidAiGuard();

  const [proposal, setProposal] = useState<CropProposal | null>(null);
  const [headerRow, setHeaderRow] = useState(false);
  const [includeNote, setIncludeNote] = useState(true);
  const [acknowledged, setAcknowledged] = useState(false);

  const grid = proposal?.grid ?? null;
  const draft = useTableDraft(grid, element ? `table-crop:${element.id}` : "");

  const readLocal = useMutation({
    mutationFn: (elementId: string) =>
      api.createElementTableProposal(projectId, elementId, { languages }),
    onSuccess: (response) => {
      draft.reset();
      setProposal({ kind: "local", grid: response });
      setAcknowledged(false);
      toast.success(t("elements.table.cropLocalReadToast"));
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const readAi = useMutation({
    mutationFn: ({
      elementId,
      confirmPaid,
    }: {
      elementId: string;
      confirmPaid: boolean;
    }) =>
      api.createAiTableProposal(projectId, elementId, {
        confirm_paid: confirmPaid,
      }),
    onSuccess: (response) => {
      // A second read replaces the grid, so corrections made against the
      // previous reply must not be applied to the new one at the same
      // coordinates.
      draft.reset();
      setProposal({ kind: "ai", grid: response });
      setAcknowledged(false);
      toast.success(t("elements.table.aiReadToast"));
    },
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => {
      // Every attempt counts against the local request limit.
      void queryClient.invalidateQueries({ queryKey: ["ai", "usage"] });
    },
  });

  useEffect(() => {
    if (!open) return;
    setProposal(null);
    setHeaderRow(false);
    setIncludeNote(true);
    setAcknowledged(false);
  }, [open, element?.id]);

  const reading = readLocal.isPending || readAi.isPending;
  const canReadLocal = Boolean(element) && ocrAvailable && !reading;
  const canReadAi =
    Boolean(element) &&
    visionModel.length > 0 &&
    !tasksQuery.isLoading &&
    !reading;
  const canInsert =
    grid !== null && (!needsTableAcknowledgement(grid) || acknowledged);

  const handleReadLocal = () => {
    if (!element || !canReadLocal) return;
    readLocal.mutate(element.id);
  };

  const handleReadAi = async () => {
    if (!element || !canReadAi) return;
    // A paid vision connection must be approved for this read only.
    const approved = await paidAi.requestApproval(tableTask);
    if (!approved) return;
    readAi.mutate({ elementId: element.id, confirmPaid: true });
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      setProposal(null);
      setHeaderRow(false);
      setIncludeNote(true);
      setAcknowledged(false);
      draft.reset();
    }
    onOpenChange(next);
  };

  const handleInsert = () => {
    if (!proposal || !canInsert) return;
    const gridView = proposal.grid;
    const spans = proposalSpans(gridView);
    const pageNumber = page?.page_number ?? "—";
    let note: string | null = null;
    if (includeNote) {
      if (proposal.kind === "local") {
        note = t(
          draft.changedCount > 0
            ? "elements.table.cropLocalCorrectedNote"
            : "elements.table.cropLocalSourceNote",
          { page: pageNumber },
        );
      } else {
        note = t(
          draft.changedCount > 0
            ? "elements.table.aiCorrectedNote"
            : "elements.table.aiSourceNote",
          { page: pageNumber, model: proposal.grid.model },
        );
      }
    }
    insertTable({
      rows: draft.rows,
      alignments: proposalAlignments(gridView),
      rowSpans: spans.rowSpan,
      colSpans: spans.colSpan,
      headerRow,
      note,
    });
    toast.success(t("elements.table.inserted"));
    handleOpenChange(false);
    onInserted?.();
  };

  const cropSrc =
    element?.asset_id
      ? api.assetUrl(projectId, element.asset_id, element.updated_at)
      : null;
  const pageImageUrl = page
    ? api.assetUrl(
        projectId,
        page.display_asset_id ?? page.original_asset_id,
        page.updated_at,
      )
    : null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] max-w-4xl flex-col gap-4 overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Table2 className="size-icon-sm text-primary" aria-hidden="true" />
            {t("elements.table.cropTitle", {
              page: page?.page_number ?? "—",
            })}
          </DialogTitle>
          <DialogDescription>
            {t("elements.table.cropDescription")}
          </DialogDescription>
        </DialogHeader>

        <div className="scrollbar-thin -mx-1 min-h-0 flex-1 space-y-4 overflow-y-auto px-1">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
            {cropSrc ? (
              <figure className="shrink-0 space-y-1">
                <img
                  src={cropSrc}
                  alt={t("elements.table.aiCropAlt")}
                  className="max-h-40 w-auto max-w-56 rounded-md border border-border/70 bg-muted/30 object-contain p-1"
                  draggable={false}
                />
                <figcaption className="text-2xs text-muted-foreground">
                  {t("elements.table.cropLabel")}
                </figcaption>
              </figure>
            ) : null}

            <div className="grid min-w-0 flex-1 gap-2 sm:grid-cols-2">
              <div className="space-y-1.5 rounded-md border border-border/60 bg-background/50 p-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full gap-1.5"
                  onClick={handleReadLocal}
                  disabled={!canReadLocal}
                >
                  {readLocal.isPending ? (
                    <Spinner className="size-icon-sm" />
                  ) : (
                    <ScanText />
                  )}
                  {readLocal.isPending
                    ? t("elements.table.cropLocalReading")
                    : t("elements.table.cropLocalRead")}
                </Button>
                <p className="text-2xs leading-relaxed text-muted-foreground">
                  {ocrAvailable
                    ? t("elements.table.cropLocalHint")
                    : t("elements.table.cropLocalUnavailable")}
                </p>
              </div>

              <div className="space-y-1.5 rounded-md border border-border/60 bg-background/50 p-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full gap-1.5"
                  onClick={() => void handleReadAi()}
                  disabled={!canReadAi}
                >
                  {readAi.isPending ? (
                    <Spinner className="size-icon-sm" />
                  ) : (
                    <Sparkles />
                  )}
                  {readAi.isPending
                    ? t("elements.table.aiReading")
                    : t("elements.table.aiRead")}
                </Button>
                <p className="text-2xs leading-relaxed text-muted-foreground">
                  {visionModel
                    ? t("elements.table.aiHint")
                    : t("elements.table.aiUnavailable")}
                </p>
              </div>
            </div>
          </div>

          {proposal ? (
            <div className="flex flex-wrap items-start gap-1.5 rounded-md border border-warning/30 bg-warning/5 px-2 py-1.5">
              {proposal.kind === "local" ? (
                <>
                  <Badge variant="outline">
                    <ScanText aria-hidden="true" />
                    {t("elements.table.cropLocalProposed", {
                      engine: proposal.grid.engine,
                    })}
                  </Badge>
                  <p className="text-2xs leading-relaxed text-muted-foreground">
                    {t("elements.table.cropLocalWarning")}
                  </p>
                </>
              ) : (
                <>
                  <Badge variant="warning">
                    <CircleAlert aria-hidden="true" />
                    {t("elements.table.aiProposed", {
                      model: proposal.grid.model,
                    })}
                  </Badge>
                  <p className="text-2xs leading-relaxed text-muted-foreground">
                    {t("elements.table.aiWarning")}
                  </p>
                </>
              )}
            </div>
          ) : (
            <p className="rounded-md border border-border/60 bg-background/50 px-2 py-1.5 text-2xs leading-relaxed text-muted-foreground">
              {t("elements.table.cropEmpty")}
            </p>
          )}

          {grid ? (
            <TableReview
              proposal={grid}
              draft={draft}
              sourceImageUrl={pageImageUrl}
              pageWidth={grid.page_width}
              pageHeight={grid.page_height}
              headerRow={headerRow}
              onHeaderRowChange={setHeaderRow}
              acknowledged={acknowledged}
              onAcknowledgedChange={setAcknowledged}
            />
          ) : null}
        </div>

        <DialogFooter className="mt-0 shrink-0 items-stretch gap-2 border-t border-border/60 pt-3 sm:items-center">
          <label className="mr-auto flex items-center gap-1.5 text-2xs text-muted-foreground">
            <input
              type="checkbox"
              className="size-3.5 accent-primary"
              checked={includeNote}
              onChange={(event) => setIncludeNote(event.target.checked)}
              disabled={!grid}
            />
            {t("elements.includeNote")}
          </label>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tCommon("actions.cancel")}
          </Button>
          <Button
            className="gap-1.5"
            onClick={handleInsert}
            disabled={!canInsert || reading}
          >
            <Table2 />
            {t("elements.table.aiInsert")}
          </Button>
        </DialogFooter>
      </DialogContent>
      {paidAi.paidDialog}
    </Dialog>
  );
}
