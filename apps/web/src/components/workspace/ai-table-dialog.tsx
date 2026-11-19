import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, Sparkles, Table2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type {
  AiTableResponse,
  ElementSummary,
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
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useAppSettings } from "@/hooks/use-app";
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

interface AiTableDialogProps {
  projectId: string;
  /** The saved table region whose crop is sent to the vision model. */
  element: ElementSummary | null;
  page: PageSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInserted?: () => void;
}

/**
 * Reads one saved table crop with the configured vision model and shows the
 * reply in the normal table review grid.
 *
 * The model only proposes text: every cell is unscored, nothing is written to the
 * region, and insertion stays disabled until the user acknowledges that the grid
 * must be checked against the crop. Manual cell corrections are inserted instead
 * of the raw reply, and the source note changes to say they were corrected.
 */
export function AiTableDialog({
  projectId,
  element,
  page,
  open,
  onOpenChange,
  onInserted,
}: AiTableDialogProps) {
  const { t } = useTranslation("workspace");
  const { t: tCommon } = useTranslation("common");
  const { insertTable } = useWorkspaceActions();
  const errorMessage = useApiErrorMessage();
  const queryClient = useQueryClient();
  const settingsQuery = useAppSettings();
  const visionModel = settingsQuery.data?.ai.vision.model?.trim() ?? "";
  const paidAi = usePaidAiGuard();

  const [proposal, setProposal] = useState<AiTableResponse | null>(null);
  const [headerRow, setHeaderRow] = useState(false);
  const [includeNote, setIncludeNote] = useState(true);
  const [acknowledged, setAcknowledged] = useState(false);

  const draft = useTableDraft(proposal, element ? `ai-table:${element.id}` : "");

  const transcribe = useMutation({
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
      setProposal(response);
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

  const canRead =
    Boolean(element) &&
    visionModel.length > 0 &&
    !settingsQuery.isLoading &&
    !transcribe.isPending;
  const canInsert =
    proposal !== null &&
    (!needsTableAcknowledgement(proposal) || acknowledged);

  const handleRead = async () => {
    if (!element || !canRead) return;
    // A paid vision profile must be approved for this read only.
    const approved = await paidAi.requestApproval(settingsQuery.data?.ai.vision);
    if (!approved) return;
    transcribe.mutate({ elementId: element.id, confirmPaid: true });
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
    const spans = proposalSpans(proposal);
    let note: string | null = null;
    if (includeNote) {
      note = t(
        draft.changedCount > 0
          ? "elements.table.aiCorrectedNote"
          : "elements.table.aiSourceNote",
        {
          page: page?.page_number ?? "—",
          model: proposal.model,
        },
      );
    }
    insertTable({
      rows: draft.rows,
      alignments: proposalAlignments(proposal),
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
            {t("elements.table.aiTitle", { page: page?.page_number ?? "—" })}
          </DialogTitle>
          <DialogDescription>{t("elements.table.aiDescription")}</DialogDescription>
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
                  {t("elements.table.aiCropLabel")}
                </figcaption>
              </figure>
            ) : null}

            <div className="min-w-0 flex-1 space-y-2">
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => void handleRead()}
                disabled={!canRead}
              >
                {transcribe.isPending ? (
                  <Spinner className="size-icon-sm" />
                ) : (
                  <Sparkles />
                )}
                {transcribe.isPending
                  ? t("elements.table.aiReading")
                  : t("elements.table.aiRead")}
              </Button>
              <p className="text-2xs leading-relaxed text-muted-foreground">
                {visionModel
                  ? t("elements.table.aiHint")
                  : t("elements.table.aiUnavailable")}
              </p>
              {proposal ? (
                <div className="flex flex-wrap items-start gap-1.5 rounded-md border border-warning/30 bg-warning/5 px-2 py-1.5">
                  <Badge variant="warning">
                    <CircleAlert aria-hidden="true" />
                    {t("elements.table.aiProposed", { model: proposal.model })}
                  </Badge>
                  <p className="text-2xs leading-relaxed text-muted-foreground">
                    {t("elements.table.aiWarning")}
                  </p>
                </div>
              ) : (
                <p className="rounded-md border border-border/60 bg-background/50 px-2 py-1.5 text-2xs leading-relaxed text-muted-foreground">
                  {t("elements.table.aiEmpty")}
                </p>
              )}
            </div>
          </div>

          {proposal ? (
            <TableReview
              proposal={proposal}
              draft={draft}
              sourceImageUrl={pageImageUrl}
              pageWidth={proposal.page_width}
              pageHeight={proposal.page_height}
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
              disabled={!proposal}
            />
            {t("elements.includeNote")}
          </label>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tCommon("actions.cancel")}
          </Button>
          <Button
            className="gap-1.5"
            onClick={handleInsert}
            disabled={!canInsert || transcribe.isPending}
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
