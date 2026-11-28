import { ChevronRight, CircleAlert, Sigma } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type {
  ElementSummary,
  PageEquationProposal,
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
import { EmptyState } from "@/components/ui/empty-state";
import { Spinner } from "@/components/ui/spinner";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useCreateElement } from "@/hooks/use-elements";
import { usePageEquationProposals } from "@/hooks/use-equation-proposals";

interface PageEquationsDialogProps {
  projectId: string;
  page: PageSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /**
   * Called after the chosen candidate becomes a saved equation crop. The parent
   * opens the normal equation review dialog, where the LaTeX is checked and
   * inserted; nothing is written to the document here.
   */
  onReview: (element: ElementSummary, text: string) => void;
}

/**
 * Lists the equation regions the backend read from this page's OCR layout.
 *
 * A candidate is only a rectangle plus unverified OCR text and the LaTeX
 * starting point normalised from it. Reviewing one saves the crop as an element
 * and hands it to the existing equation dialog, so the user still sees the
 * KaTeX preview and confirms the insert. Inline math inside a paragraph is never
 * proposed because it is not a separate block.
 */
export function PageEquationsDialog({
  projectId,
  page,
  open,
  onOpenChange,
  onReview,
}: PageEquationsDialogProps) {
  const { t } = useTranslation("workspace");
  const errorMessage = useApiErrorMessage();
  const proposalsQuery = usePageEquationProposals(
    projectId,
    page?.id ?? null,
    open,
  );
  const createElement = useCreateElement(projectId, page?.id ?? "");
  const [pendingKey, setPendingKey] = useState<string | null>(null);

  const body = proposalsQuery.data;
  const proposals = body?.proposals ?? [];

  const statusMessage = (status: string | undefined) => {
    switch (status) {
      case "no_ocr_run":
        return t("ocr.equation.status.noOcrRun");
      case "ocr_not_ready":
        return t("ocr.equation.status.notReady");
      case "ocr_failed":
        return t("ocr.equation.status.failed");
      case "ocr_stale":
        return t("ocr.equation.status.stale");
      case "no_geometry":
        return t("ocr.equation.status.noGeometry");
      default:
        return t("ocr.equation.emptyDescription");
    }
  };

  const handleReview = async (candidate: PageEquationProposal) => {
    if (!page || pendingKey !== null) return;
    setPendingKey(candidate.key);
    try {
      const element = await createElement.mutateAsync({
        kind: "equation",
        x: candidate.x,
        y: candidate.y,
        width: candidate.width,
        height: candidate.height,
        caption: "",
      });
      onReview(element, candidate.latex || candidate.text);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setPendingKey(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] max-w-2xl flex-col gap-4 overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sigma className="size-icon-sm text-primary" aria-hidden="true" />
            {t("ocr.equation.detectTitle", { page: page?.page_number ?? "—" })}
          </DialogTitle>
          <DialogDescription>
            {t("ocr.equation.detectDescription")}
          </DialogDescription>
        </DialogHeader>

        {proposalsQuery.isLoading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-xs text-muted-foreground">
            <Spinner className="size-icon-lg text-primary" />
            <span>{t("ocr.equation.loading")}</span>
          </div>
        ) : proposalsQuery.isError ? (
          <EmptyState
            compact
            icon={CircleAlert}
            title={t("ocr.equation.errorTitle")}
            description={errorMessage(proposalsQuery.error)}
            action={
              <Button
                variant="outline"
                size="sm"
                onClick={() => void proposalsQuery.refetch()}
              >
                {t("ocr.equation.retry")}
              </Button>
            }
          />
        ) : !body || body.status !== "ready" ? (
          <EmptyState
            compact
            icon={Sigma}
            title={t("ocr.equation.statusTitle")}
            description={statusMessage(body?.status)}
          />
        ) : proposals.length === 0 ? (
          <EmptyState
            compact
            icon={Sigma}
            title={t("ocr.equation.emptyTitle")}
            description={t("ocr.equation.emptyDescription")}
          />
        ) : (
          <>
            <p className="text-2xs text-muted-foreground">
              {t("ocr.equation.count", { count: proposals.length })}
            </p>
            <ul className="scrollbar-thin min-h-0 flex-1 space-y-2 overflow-auto">
              {proposals.map((item) => {
                const reviewing = pendingKey === item.key;
                return (
                  <li key={item.key}>
                    <button
                      type="button"
                      className="flex w-full items-center gap-3 rounded-lg border border-border/70 bg-background/50 p-3 text-left transition-colors hover:border-primary/40 hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
                      onClick={() => void handleReview(item)}
                      disabled={pendingKey !== null}
                    >
                      <Sigma
                        className="size-icon-sm shrink-0 text-primary"
                        aria-hidden="true"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="flex flex-wrap items-center gap-1.5">
                          <span className="text-xs font-medium">
                            {t("ocr.equation.candidate", {
                              index: item.reading_index + 1,
                            })}
                          </span>
                          <Badge variant="outline">
                            {t("ocr.equation.display")}
                          </Badge>
                          <Badge variant="secondary">
                            {t(`ocr.equation.confidence.${item.confidence}`)}
                          </Badge>
                        </span>
                        <span className="mt-1 block truncate text-2xs text-muted-foreground">
                          {item.text || t("ocr.equation.noText")}
                        </span>
                      </span>
                      {reviewing ? (
                        <Spinner className="size-icon-sm shrink-0 text-primary" />
                      ) : (
                        <ChevronRight
                          className="size-icon-sm shrink-0 text-muted-foreground"
                          aria-hidden="true"
                        />
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </>
        )}

        <DialogFooter className="mt-0 shrink-0 items-stretch gap-2 border-t border-border/60 pt-3 sm:items-center">
          <Button
            variant="outline"
            className="ml-auto"
            onClick={() => onOpenChange(false)}
          >
            {t("ocr.equation.dismiss")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
