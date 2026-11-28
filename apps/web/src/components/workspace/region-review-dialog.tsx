import {
  ChevronRight,
  CircleAlert,
  FileImage,
  LayoutList,
  Sigma,
  Table2,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import type { RegionProposal } from "@docurebuild/shared-types";

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
import { useProjectRegionProposals } from "@/hooks/use-elements";

interface RegionReviewDialogProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Navigate to a page without choosing a suggestion. */
  onOpenPage: (pageId: string) => void;
  /**
   * Navigate to the proposal's page and open the normal element review dialog.
   * The aggregation itself never saves a crop.
   */
  onReviewProposal: (pageId: string, proposal: RegionProposal) => void;
}

const KIND_ICONS: Record<string, LucideIcon> = {
  figure: FileImage,
  table: Table2,
  equation: Sigma,
};

/**
 * Read-only overview of region suggestions across pages.
 *
 * The list is derived from each page's latest successful OCR run by the same
 * backend function that powers the per-page overlay, so a suggestion carries the
 * same `ocr_run_id`, source asset and rotation identity. Nothing is persisted and
 * no crop is created here; selecting an entry only navigates to the page and
 * hands the rectangle to the existing review flow.
 */
export function RegionReviewDialog({
  projectId,
  open,
  onOpenChange,
  onOpenPage,
  onReviewProposal,
}: RegionReviewDialogProps) {
  const { t } = useTranslation("workspace");
  const errorMessage = useApiErrorMessage();
  const proposalsQuery = useProjectRegionProposals(projectId, open);
  const body = proposalsQuery.data;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] max-w-3xl flex-col gap-4 overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <LayoutList className="size-icon-sm text-primary" aria-hidden="true" />
            {t("elements.review.title")}
          </DialogTitle>
          <DialogDescription>{t("elements.review.description")}</DialogDescription>
        </DialogHeader>

        {proposalsQuery.isLoading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-xs text-muted-foreground">
            <Spinner className="size-icon-lg text-primary" />
            <span>{t("elements.review.loading")}</span>
          </div>
        ) : proposalsQuery.isError ? (
          <EmptyState
            compact
            icon={CircleAlert}
            title={t("elements.review.errorTitle")}
            description={errorMessage(proposalsQuery.error)}
            action={
              <Button
                variant="outline"
                size="sm"
                onClick={() => void proposalsQuery.refetch()}
              >
                {t("elements.review.retry")}
              </Button>
            }
          />
        ) : !body || body.pages_with_proposals === 0 ? (
          <EmptyState
            compact
            icon={LayoutList}
            title={t("elements.review.emptyTitle")}
            description={t("elements.review.emptyDescription")}
          />
        ) : (
          <>
            <p className="text-2xs text-muted-foreground">
              {t("elements.review.summary", {
                pages: body.pages_with_proposals,
                count: body.total_proposals,
              })}
            </p>
            <ul className="scrollbar-thin min-h-0 flex-1 space-y-3 overflow-auto">
              {body.pages.map((page) => (
                <li
                  key={page.page_id}
                  className="overflow-hidden rounded-lg border border-border/70 bg-background/40"
                >
                  <div className="flex items-center gap-2 border-b border-border/60 bg-background/30 px-3 py-2">
                    <span className="text-xs font-semibold">
                      {t("elements.review.page", { page: page.page_number })}
                    </span>
                    <Badge variant="secondary">
                      {t("elements.review.proposalCount", {
                        count: page.proposal_count,
                      })}
                    </Badge>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="ml-auto"
                      onClick={() => onOpenPage(page.page_id)}
                    >
                      {t("elements.review.openPage")}
                    </Button>
                  </div>
                  <ul className="divide-y divide-border/60">
                    {page.proposals.map((proposal) => {
                      const Icon = KIND_ICONS[proposal.kind] ?? LayoutList;
                      return (
                        <li key={proposal.key}>
                          <button
                            type="button"
                            className="flex w-full items-center gap-3 px-3 py-2 text-left transition-colors hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                            onClick={() => onReviewProposal(page.page_id, proposal)}
                          >
                            <Icon
                              className="size-icon-sm shrink-0 text-primary"
                              aria-hidden="true"
                            />
                            <span className="min-w-0 flex-1">
                              <span className="flex flex-wrap items-center gap-1.5">
                                <span className="text-xs font-medium">
                                  {t(`elements.kind.${proposal.kind}`)}
                                </span>
                                <Badge variant="outline">
                                  {t(`elements.proposals.source.${proposal.reason}`)}
                                </Badge>
                                <Badge variant="secondary">
                                  {t(
                                    `elements.review.confidence.${proposal.confidence}`,
                                  )}
                                </Badge>
                              </span>
                              {proposal.caption ? (
                                <span className="mt-0.5 block truncate text-2xs text-muted-foreground">
                                  {proposal.caption}
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
                </li>
              ))}
            </ul>
            {body.truncated ? (
              <p className="shrink-0 text-2xs text-muted-foreground">
                {t("elements.review.truncated", {
                  page: body.next_page_number ?? "—",
                })}
              </p>
            ) : null}
          </>
        )}

        <DialogFooter className="mt-0 shrink-0 items-stretch gap-2 border-t border-border/60 pt-3 sm:items-center">
          <Button
            variant="outline"
            className="ml-auto"
            onClick={() => onOpenChange(false)}
          >
            {t("elements.review.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
