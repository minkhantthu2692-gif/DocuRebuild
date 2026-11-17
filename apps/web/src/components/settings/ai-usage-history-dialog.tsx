import { CircleAlert, History, Sparkles } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type {
  AiUsageHistoryEntry,
  AiUsageOutcome,
  AiUsageTask,
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CenteredSpinner } from "@/components/ui/spinner";
import { useAiUsageHistory, type AiUsageHistoryParams } from "@/hooks/use-ai";
import { formatDateTime, formatNumber, resolveLocale } from "@/lib/format";

const PAGE_SIZE = 25;

const OUTCOMES: readonly AiUsageOutcome[] = ["success", "error"];
const TASKS: readonly AiUsageTask[] = [
  "ocr_cleanup",
  "region_proposals",
  "equation_transcription",
];

interface AiUsageHistoryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function filterValue<T extends string>(value: string): T | "all" {
  return value === "all" ? "all" : (value as T);
}

/**
 * Browses the full local AI ledger beyond the last five rows in Settings.
 *
 * The ledger is metadata only: provider, model, task, outcome, error code,
 * project/page ids and time. It never stores document text, the crop or the
 * model's reply, so this view cannot leak content. Rows for deleted projects
 * stay visible with no project name.
 */
export function AiUsageHistoryDialog({
  open,
  onOpenChange,
}: AiUsageHistoryDialogProps) {
  const { t, i18n } = useTranslation("settings");
  const { t: tCommon } = useTranslation("common");
  const locale = resolveLocale(i18n.resolvedLanguage);

  const [outcome, setOutcome] = useState<AiUsageOutcome | "all">("all");
  const [task, setTask] = useState<AiUsageTask | "all">("all");
  const [offset, setOffset] = useState(0);

  const params: AiUsageHistoryParams = {
    limit: PAGE_SIZE,
    offset,
    ...(outcome === "all" ? {} : { outcome }),
    ...(task === "all" ? {} : { task }),
  };
  const query = useAiUsageHistory(params, open);
  const entries = query.data?.entries ?? [];
  const total = query.data?.total ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + entries.length, total);
  const canGoBack = offset > 0;
  const canGoForward = offset + PAGE_SIZE < total;

  const changeOutcome = (value: string) => {
    setOutcome(filterValue<AiUsageOutcome>(value));
    setOffset(0);
  };
  const changeTask = (value: string) => {
    setTask(filterValue<AiUsageTask>(value));
    setOffset(0);
  };

  const taskLabel = (value: string) =>
    TASKS.includes(value as AiUsageTask)
      ? t(`ai.tasks.${value}`)
      : t("ai.history.unknownTask");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] max-w-3xl flex-col gap-4 overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <History className="size-icon-sm text-primary" aria-hidden="true" />
            {t("ai.history.title")}
          </DialogTitle>
          <DialogDescription>{t("ai.history.description")}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-end gap-2">
          <div className="w-40 space-y-1">
            <p className="text-2xs font-medium text-muted-foreground">
              {t("ai.history.outcomeFilter")}
            </p>
            <Select value={outcome} onValueChange={changeOutcome}>
              <SelectTrigger className="h-control" aria-label={t("ai.history.outcomeFilter")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("ai.history.outcomes.all")}</SelectItem>
                {OUTCOMES.map((value) => (
                  <SelectItem key={value} value={value}>
                    {t(`ai.history.outcomes.${value}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-48 space-y-1">
            <p className="text-2xs font-medium text-muted-foreground">
              {t("ai.history.taskFilter")}
            </p>
            <Select value={task} onValueChange={changeTask}>
              <SelectTrigger className="h-control" aria-label={t("ai.history.taskFilter")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("ai.history.allTasks")}</SelectItem>
                {TASKS.map((value) => (
                  <SelectItem key={value} value={value}>
                    {t(`ai.tasks.${value}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <p className="ml-auto pb-2 text-2xs text-muted-foreground">
            {total > 0
              ? t("ai.history.showing", {
                  from: formatNumber(from, locale),
                  to: formatNumber(to, locale),
                  total: formatNumber(total, locale),
                })
              : null}
          </p>
        </div>

        <div className="scrollbar-thin -mx-1 min-h-0 flex-1 overflow-y-auto px-1">
          {query.isLoading ? (
            <CenteredSpinner label={t("ai.history.loading")} />
          ) : query.isError ? (
            <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/5 p-3 text-xs">
              <CircleAlert
                className="mt-0.5 size-icon-sm shrink-0 text-warning"
                aria-hidden="true"
              />
              <div className="space-y-2">
                <p>{t("ai.history.error")}</p>
                <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
                  {tCommon("actions.retry")}
                </Button>
              </div>
            </div>
          ) : entries.length === 0 ? (
            <EmptyState
              icon={Sparkles}
              title={t("ai.history.emptyTitle")}
              description={t("ai.history.empty")}
            />
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border/70 bg-background/40">
              <table className="w-full min-w-[40rem] border-collapse text-xs">
                <thead className="bg-muted/30 text-2xs uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th scope="col" className="px-3 py-2 text-left font-medium">
                      {t("ai.history.time")}
                    </th>
                    <th scope="col" className="px-3 py-2 text-left font-medium">
                      {t("ai.history.task")}
                    </th>
                    <th scope="col" className="px-3 py-2 text-left font-medium">
                      {t("ai.history.project")}
                    </th>
                    <th scope="col" className="px-3 py-2 text-left font-medium">
                      {t("ai.history.model")}
                    </th>
                    <th scope="col" className="px-3 py-2 text-left font-medium">
                      {t("ai.history.outcome")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {entries.map((entry: AiUsageHistoryEntry) => (
                    <tr key={entry.id}>
                      <td className="whitespace-nowrap px-3 py-2 text-muted-foreground">
                        {formatDateTime(entry.created_at, locale)}
                      </td>
                      <td className="px-3 py-2">
                        <span>{taskLabel(entry.task)}</span>
                        {entry.error_code ? (
                          <span className="block font-mono text-2xs text-destructive">
                            {entry.error_code}
                          </span>
                        ) : null}
                      </td>
                      <td className="px-3 py-2">
                        {entry.project_name ?? (
                          <span className="italic text-muted-foreground">
                            {t("ai.history.noProject")}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <span className="block max-w-40 truncate">{entry.model}</span>
                        <span className="block text-2xs text-muted-foreground">
                          {entry.provider}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <Badge
                          variant={entry.outcome === "success" ? "success" : "warning"}
                        >
                          {t(`ai.history.outcomes.${entry.outcome}`)}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!canGoBack || query.isFetching}
              onClick={() => setOffset(Math.max(offset - PAGE_SIZE, 0))}
            >
              {t("ai.history.previous")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!canGoForward || query.isFetching}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              {t("ai.history.next")}
            </Button>
          </div>
          <p className="text-2xs leading-relaxed text-muted-foreground">
            {t("ai.history.privacy")}
          </p>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tCommon("actions.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
