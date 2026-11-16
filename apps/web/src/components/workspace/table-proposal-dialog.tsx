import { CircleAlert, Table2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type { OcrBlock, PageSummary } from "@docurebuild/shared-types";

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
import { useTableProposal } from "@/hooks/use-table-proposal";
import { api } from "@/lib/api";
import { needsTableAcknowledgement } from "@/lib/table-candidates";
import { TableReview } from "./table-review";
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
  const draft = useTableDraft(proposal, block ? `block:${block.id}` : "");
  const resetDraft = draft.reset;

  const [headerRow, setHeaderRow] = useState(false);
  const [includeNote, setIncludeNote] = useState(true);
  const [acknowledged, setAcknowledged] = useState(false);

  useEffect(() => {
    if (!open) return;
    setHeaderRow(false);
    setIncludeNote(true);
    setAcknowledged(false);
    resetDraft();
  }, [open, block?.id, resetDraft]);

  const needsReview = proposal ? needsTableAcknowledgement(proposal) : false;
  const canInsert = Boolean(proposal) && (!needsReview || acknowledged);
  const sourceImageUrl = page
    ? api.assetUrl(
        projectId,
        page.display_asset_id ?? page.original_asset_id,
        page.updated_at,
      )
    : null;

  const handleInsert = () => {
    if (!proposal || !canInsert) return;
    insertTable({
      rows: draft.rows,
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
          <TableReview
            proposal={proposal}
            draft={draft}
            sourceImageUrl={sourceImageUrl}
            pageWidth={proposal.page_width}
            pageHeight={proposal.page_height}
            headerRow={headerRow}
            onHeaderRowChange={setHeaderRow}
            acknowledged={acknowledged}
            onAcknowledgedChange={setAcknowledged}
          />
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
