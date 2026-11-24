import { Check, CircleAlert, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type { AiSuggestion } from "@docurebuild/shared-types";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { CenteredSpinner } from "@/components/ui/spinner";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import {
  useBulkDecideAiSuggestions,
  useDecideAiSuggestion,
  useProjectAiSuggestions,
} from "@/hooks/use-ai";
import { formatDateTime, resolveLocale } from "@/lib/format";
import { ProposalDiff } from "./proposal-diff";

interface AiReviewDialogProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface SuggestionCardProps {
  suggestion: AiSuggestion;
  busy: boolean;
  disabled: boolean;
  selected: boolean;
  onToggleSelected: (suggestionId: string) => void;
  providerLabel: string;
  timeLabel: string;
  onDecide: (suggestion: AiSuggestion, status: "accepted" | "rejected") => void;
}

function SuggestionCard({
  suggestion,
  busy,
  disabled,
  selected,
  onToggleSelected,
  providerLabel,
  timeLabel,
  onDecide,
}: SuggestionCardProps) {
  const { t } = useTranslation("workspace");
  const pageLabel =
    suggestion.page_number === null
      ? t("aiReview.unknownPage")
      : t("aiReview.page", { page: suggestion.page_number });
  const preview = suggestion.original_text.slice(0, 40);

  return (
    <li className="rounded-lg border border-border/70 bg-background/45 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Checkbox
          checked={selected}
          disabled={disabled || busy}
          aria-label={t("aiReview.selectProposal", { page: pageLabel, text: preview })}
          onChange={() => onToggleSelected(suggestion.id)}
        />
        <Badge variant="outline">{pageLabel}</Badge>
        <span className="min-w-0 truncate text-2xs text-muted-foreground">
          {providerLabel} · {timeLabel}
        </span>
        <Badge variant="warning" className="ml-auto">
          {t("aiReview.unverified")}
        </Badge>
      </div>

      <div className="mt-2">
        <ProposalDiff
          original={suggestion.original_text}
          proposed={suggestion.proposed_text}
          originalLabel={t("aiReview.original")}
          proposedLabel={t("aiReview.proposed")}
        />
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          className="gap-1.5"
          disabled={disabled || busy}
          onClick={() => onDecide(suggestion, "accepted")}
        >
          <Check />
          {t("aiReview.accept")}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          disabled={disabled || busy}
          onClick={() => onDecide(suggestion, "rejected")}
        >
          <X />
          {t("aiReview.reject")}
        </Button>
        {busy ? (
          <span className="text-2xs text-muted-foreground">{t("aiReview.working")}</span>
        ) : null}
      </div>
    </li>
  );
}

export function AiReviewDialog({ projectId, open, onOpenChange }: AiReviewDialogProps) {
  const { t, i18n } = useTranslation("workspace");
  const { t: tCommon } = useTranslation("common");
  const locale = resolveLocale(i18n.resolvedLanguage);
  const errorMessage = useApiErrorMessage();
  const query = useProjectAiSuggestions(projectId, "pending", open);
  const decide = useDecideAiSuggestion(projectId);
  const bulk = useBulkDecideAiSuggestions(projectId);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [confirmAction, setConfirmAction] = useState<"accepted" | "rejected" | null>(
    null,
  );

  const suggestions = query.data?.suggestions ?? [];
  const pendingIds = new Set(suggestions.map((suggestion) => suggestion.id));
  const selectedIds = [...selected].filter((id) => pendingIds.has(id));
  const selectedCount = selectedIds.length;
  const allSelected = suggestions.length > 0 && selectedCount === suggestions.length;
  const someSelected = selectedCount > 0 && !allSelected;

  const decidingId = decide.isPending
    ? (decide.variables?.suggestionId ?? null)
    : null;
  const otherDecisionRunning = decide.isPending || bulk.isPending;

  useEffect(() => {
    if (!open) {
      setSelected(new Set());
      setConfirmAction(null);
    }
  }, [open]);

  const toggleSelected = (suggestionId: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(suggestionId)) {
        next.delete(suggestionId);
      } else {
        next.add(suggestionId);
      }
      return next;
    });
  };

  const toggleAll = () => {
    setSelected(
      allSelected ? new Set() : new Set(suggestions.map((suggestion) => suggestion.id)),
    );
  };

  const decideOne = (
    suggestion: AiSuggestion,
    status: "accepted" | "rejected",
  ) => {
    decide.mutate(
      { suggestionId: suggestion.id, payload: { status } },
      {
        onSuccess: () => {
          toast.success(
            t(status === "accepted" ? "aiReview.accepted" : "aiReview.rejected"),
          );
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  };

  const runBulk = () => {
    if (!confirmAction || selectedIds.length === 0) return;
    const status = confirmAction;
    bulk.mutate(
      { ids: selectedIds, status },
      {
        onSuccess: (result) => {
          setSelected(new Set());
          setConfirmAction(null);
          if (result.failed === 0) {
            toast.success(
              t(
                status === "accepted"
                  ? "aiReview.bulkAccepted"
                  : "aiReview.bulkRejected",
                { count: result.succeeded },
              ),
            );
          } else if (result.succeeded === 0) {
            toast.error(
              t("aiReview.bulkAllFailed", { failed: result.failed }),
            );
          } else {
            toast.warning(
              t("aiReview.bulkPartial", {
                succeeded: result.succeeded,
                failed: result.failed,
              }),
            );
          }
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] max-w-3xl flex-col gap-4 overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="size-icon-sm text-primary" aria-hidden="true" />
            {t("aiReview.title")}
          </DialogTitle>
          <DialogDescription>{t("aiReview.description")}</DialogDescription>
        </DialogHeader>

        <div className="scrollbar-thin -mx-1 min-h-0 flex-1 overflow-y-auto px-1">
          {query.isLoading ? (
            <CenteredSpinner label={t("aiReview.loading")} />
          ) : query.isError ? (
            <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/5 p-3 text-xs">
              <CircleAlert className="mt-0.5 size-icon-sm shrink-0 text-warning" aria-hidden="true" />
              <div className="space-y-2">
                <p>{t("aiReview.error")}</p>
                <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
                  {t("aiReview.retry")}
                </Button>
              </div>
            </div>
          ) : suggestions.length === 0 ? (
            <EmptyState
              icon={Sparkles}
              title={t("aiReview.emptyTitle")}
              description={t("aiReview.empty")}
            />
          ) : (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border/70 bg-background/50 px-3 py-2">
                <label className="flex items-center gap-1.5 text-2xs text-muted-foreground">
                  <Checkbox
                    checked={allSelected}
                    indeterminate={someSelected}
                    aria-label={t("aiReview.selectAll")}
                    disabled={bulk.isPending}
                    onChange={toggleAll}
                  />
                  {t("aiReview.selectAll")}
                </label>
                <span className="text-2xs text-muted-foreground">
                  {t("aiReview.selectedCount", { count: selectedCount })}
                </span>
                <div className="ml-auto flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={selectedCount === 0 || otherDecisionRunning}
                    onClick={() => setConfirmAction("rejected")}
                  >
                    {t("aiReview.rejectSelected")}
                  </Button>
                  <Button
                    size="sm"
                    disabled={selectedCount === 0 || otherDecisionRunning}
                    onClick={() => setConfirmAction("accepted")}
                  >
                    {t("aiReview.acceptSelected")}
                  </Button>
                </div>
              </div>

              {confirmAction ? (
                <div
                  role="group"
                  aria-label={t(
                    confirmAction === "accepted"
                      ? "aiReview.bulkAcceptConfirmTitle"
                      : "aiReview.bulkRejectConfirmTitle",
                  )}
                  className="space-y-2 rounded-lg border border-primary/30 bg-primary/5 p-3 text-xs"
                >
                  <p className="leading-relaxed">
                    {t(
                      confirmAction === "accepted"
                        ? "aiReview.bulkAcceptConfirm"
                        : "aiReview.bulkRejectConfirm",
                      { count: selectedCount },
                    )}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      disabled={bulk.isPending || selectedCount === 0}
                      onClick={runBulk}
                    >
                      {bulk.isPending
                        ? t("aiReview.bulkWorking")
                        : t(
                            confirmAction === "accepted"
                              ? "aiReview.bulkAccept"
                              : "aiReview.bulkReject",
                            { count: selectedCount },
                          )}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={bulk.isPending}
                      onClick={() => setConfirmAction(null)}
                    >
                      {tCommon("actions.cancel")}
                    </Button>
                  </div>
                </div>
              ) : null}

              <ul className="space-y-2">
                {suggestions.map((suggestion) => (
                  <SuggestionCard
                    key={suggestion.id}
                    suggestion={suggestion}
                    busy={decidingId === suggestion.id}
                    disabled={otherDecisionRunning && decidingId !== suggestion.id}
                    selected={selected.has(suggestion.id)}
                    onToggleSelected={toggleSelected}
                    providerLabel={t(`ocr.ai.providers.${suggestion.provider}`)}
                    timeLabel={formatDateTime(suggestion.created_at, locale)}
                    onDecide={decideOne}
                  />
                ))}
              </ul>
            </div>
          )}
        </div>

        <p className="rounded-lg border border-border/60 bg-background/50 p-3 text-2xs leading-relaxed text-muted-foreground">
          {t("aiReview.note")}
        </p>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tCommon("actions.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
