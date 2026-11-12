import { Check, CircleAlert, Sparkles, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type { AiSuggestion } from "@docurebuild/shared-types";

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
import { CenteredSpinner } from "@/components/ui/spinner";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useDecideAiSuggestion, useProjectAiSuggestions } from "@/hooks/use-ai";
import { formatDateTime, resolveLocale } from "@/lib/format";

interface AiReviewDialogProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface SuggestionCardProps {
  suggestion: AiSuggestion;
  busy: boolean;
  disabled: boolean;
  providerLabel: string;
  timeLabel: string;
  onDecide: (suggestion: AiSuggestion, status: "accepted" | "rejected") => void;
}

function SuggestionCard({
  suggestion,
  busy,
  disabled,
  providerLabel,
  timeLabel,
  onDecide,
}: SuggestionCardProps) {
  const { t } = useTranslation("workspace");
  const pageLabel =
    suggestion.page_number === null
      ? t("aiReview.unknownPage")
      : t("aiReview.page", { page: suggestion.page_number });

  return (
    <li className="rounded-lg border border-border/70 bg-background/45 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{pageLabel}</Badge>
        <span className="min-w-0 truncate text-2xs text-muted-foreground">
          {providerLabel} · {timeLabel}
        </span>
        <Badge variant="warning" className="ml-auto">
          {t("aiReview.unverified")}
        </Badge>
      </div>

      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <div className="min-w-0 rounded-md border border-border/60 bg-background/50 p-2">
          <p className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
            {t("aiReview.original")}
          </p>
          <p className="mt-1 whitespace-pre-wrap break-words text-xs leading-relaxed">
            {suggestion.original_text}
          </p>
        </div>
        <div className="min-w-0 rounded-md border border-primary/25 bg-primary/5 p-2">
          <p className="text-2xs font-semibold uppercase tracking-wider text-primary">
            {t("aiReview.proposed")}
          </p>
          <p className="mt-1 whitespace-pre-wrap break-words text-xs leading-relaxed">
            {suggestion.proposed_text}
          </p>
        </div>
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

  const suggestions = query.data?.suggestions ?? [];
  const decidingId = decide.isPending
    ? (decide.variables?.suggestionId ?? null)
    : null;
  const otherDecisionRunning = decide.isPending;

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
            <ul className="space-y-2">
              {suggestions.map((suggestion) => (
                <SuggestionCard
                  key={suggestion.id}
                  suggestion={suggestion}
                  busy={decidingId === suggestion.id}
                  disabled={otherDecisionRunning && decidingId !== suggestion.id}
                  providerLabel={t(`ocr.ai.providers.${suggestion.provider}`)}
                  timeLabel={formatDateTime(suggestion.created_at, locale)}
                  onDecide={decideOne}
                />
              ))}
            </ul>
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
