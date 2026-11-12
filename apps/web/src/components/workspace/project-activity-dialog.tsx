import type { TFunction } from "i18next";
import { Activity, CircleAlert, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import type { HistoryEvent } from "@docurebuild/shared-types";

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
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CenteredSpinner } from "@/components/ui/spinner";
import { useProjectHistory } from "@/hooks/use-projects";
import {
  ACTIVITY_CATEGORIES,
  activitySearchText,
  filterActivityEvents,
  type ActivityCategory,
} from "@/lib/activity-filter";
import {
  formatDateTime,
  formatFileSize,
  formatNumber,
  resolveLocale,
} from "@/lib/format";

interface ProjectActivityDialogProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Event types this build can label in the current language. Unknown types still
 * appear, with the recorded English summary as a fallback, so an older project
 * database never hides activity.
 */
const KNOWN_EVENTS = new Set([
  "project_created",
  "project_backup_created",
  "project_restored",
  "pages_imported",
  "pages_import_cancelled",
  "page_processed",
  "page_edits_reset",
  "page_deleted",
  "element_extracted",
  "element_updated",
  "element_text_extracted",
  "element_text_updated",
  "element_deleted",
  "document_exported",
  "ocr_started",
  "ocr_succeeded",
  "ocr_failed",
]);

function eventDetails(event: HistoryEvent, t: TFunction, locale: string): string[] {
  const payload = event.payload ?? {};
  const details: string[] = [];

  if (event.event_type === "pages_imported" && typeof payload.count === "number") {
    details.push(t("activity.details.imported", { count: payload.count }));
  }
  if (
    event.event_type === "pages_import_cancelled" &&
    typeof payload.count === "number"
  ) {
    details.push(t("activity.details.importedCancelled", { count: payload.count }));
  }
  if (event.event_type === "document_exported") {
    const format = payload.format === "txt" ? t("export.txt") : t("export.markdown");
    details.push(t("activity.details.exported", { format }));
    if (typeof payload.byte_size === "number") {
      details.push(
        t("activity.details.size", {
          size: formatFileSize(payload.byte_size, locale),
        }),
      );
    }
  }
  if (
    event.event_type === "project_backup_created" &&
    typeof payload.byte_size === "number"
  ) {
    details.push(
      t("activity.details.backup", {
        size: formatFileSize(payload.byte_size, locale),
      }),
    );
  }
  if (event.event_type.startsWith("ocr_")) {
    if (typeof payload.languages === "string") {
      details.push(t("activity.details.languages", { languages: payload.languages }));
    }
    if (
      event.event_type === "ocr_succeeded" &&
      typeof payload.mean_confidence === "number"
    ) {
      details.push(
        t("activity.details.confidence", {
          value: formatNumber(payload.mean_confidence, locale),
        }),
      );
    }
    if (event.event_type === "ocr_succeeded" && typeof payload.blocks === "number") {
      details.push(t("activity.details.blocks", { count: payload.blocks }));
    }
    if (event.event_type === "ocr_failed" && typeof payload.error_code === "string") {
      details.push(t("activity.details.errorCode", { code: payload.error_code }));
    }
  }

  return details;
}

export function ProjectActivityDialog({
  projectId,
  open,
  onOpenChange,
}: ProjectActivityDialogProps) {
  const { t, i18n } = useTranslation("workspace");
  const { t: tCommon } = useTranslation("common");
  const locale = resolveLocale(i18n.language);
  const query = useProjectHistory(projectId, open);
  const events = useMemo(() => query.data ?? [], [query.data]);
  const [category, setCategory] = useState<ActivityCategory>("all");
  const [search, setSearch] = useState("");

  const filtersActive = category !== "all" || search.trim() !== "";
  const clearFilters = () => {
    setCategory("all");
    setSearch("");
  };

  const filteredEvents = useMemo(() => {
    const textFor = (event: HistoryEvent) => {
      const label = KNOWN_EVENTS.has(event.event_type)
        ? t(`activity.events.${event.event_type}`)
        : t("activity.unknown");
      return [label, ...eventDetails(event, t, locale), activitySearchText(event)].join(" ");
    };
    return filterActivityEvents(events, category, search, textFor);
  }, [events, category, search, t, locale]);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) clearFilters();
        onOpenChange(next);
      }}
    >
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] max-w-2xl flex-col gap-4 overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Activity className="size-icon-sm text-primary" aria-hidden="true" />
            {t("activity.title")}
          </DialogTitle>
          <DialogDescription>{t("activity.description")}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            disabled={query.isFetching}
            onClick={() => void query.refetch()}
          >
            {t("activity.refresh")}
          </Button>
          {filtersActive ? (
            <Button variant="ghost" size="sm" onClick={clearFilters}>
              {t("activity.filters.clear")}
            </Button>
          ) : null}
          <span className="ml-auto text-2xs text-muted-foreground" role="status">
            {filtersActive
              ? t("activity.filters.filteredCount", {
                  shown: filteredEvents.length,
                  total: events.length,
                })
              : t("activity.count", { count: events.length })}
          </span>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          <div className="space-y-1">
            <label className="text-2xs font-medium text-muted-foreground">
              {t("activity.filters.category")}
            </label>
            <Select
              value={category}
              onValueChange={(value) => setCategory(value as ActivityCategory)}
            >
              <SelectTrigger aria-label={t("activity.filters.category")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ACTIVITY_CATEGORIES.map((value) => (
                  <SelectItem key={value} value={value}>
                    {t(`activity.filters.${value}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <label
              htmlFor="activity-search"
              className="text-2xs font-medium text-muted-foreground"
            >
              {t("activity.filters.search")}
            </label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-icon-sm -translate-y-1/2 text-muted-foreground" />
              <Input
                id="activity-search"
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t("activity.filters.searchPlaceholder")}
                className="pl-9"
                aria-label={t("activity.filters.search")}
              />
            </div>
          </div>
        </div>

        <div className="scrollbar-thin -mx-1 min-h-0 flex-1 overflow-y-auto px-1">
          {query.isLoading ? (
            <CenteredSpinner label={t("activity.loading")} />
          ) : query.isError ? (
            <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/5 p-3 text-xs">
              <CircleAlert
                className="mt-0.5 size-icon-sm shrink-0 text-warning"
                aria-hidden="true"
              />
              <div className="space-y-2">
                <p>{t("activity.error")}</p>
                <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
                  {t("activity.retry")}
                </Button>
              </div>
            </div>
          ) : events.length === 0 ? (
            <EmptyState
              icon={Activity}
              title={t("activity.emptyTitle")}
              description={t("activity.empty")}
              compact
            />
          ) : filteredEvents.length === 0 ? (
            <EmptyState
              icon={Search}
              title={t("activity.filters.noMatchesTitle")}
              description={t("activity.filters.noMatches")}
              action={
                <Button variant="outline" size="sm" onClick={clearFilters}>
                  {t("activity.filters.showAll")}
                </Button>
              }
              compact
            />
          ) : (
            <ul className="space-y-2">
              {filteredEvents.map((event) => {
                const known = KNOWN_EVENTS.has(event.event_type);
                const details = eventDetails(event, t, locale);
                return (
                  <li
                    key={event.id}
                    className="rounded-lg border border-border/70 bg-background/45 p-3"
                  >
                    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                      <span className="text-xs font-medium">
                        {known
                          ? t(`activity.events.${event.event_type}`)
                          : t("activity.unknown")}
                      </span>
                      <time
                        dateTime={event.created_at}
                        className="ml-auto text-2xs text-muted-foreground"
                      >
                        {formatDateTime(event.created_at, locale)}
                      </time>
                    </div>
                    {details.length > 0 ? (
                      <p className="mt-1 text-2xs leading-relaxed text-muted-foreground">
                        {details.join(" · ")}
                      </p>
                    ) : null}
                    {!known && event.summary ? (
                      <p className="mt-1 text-2xs leading-relaxed text-muted-foreground">
                        {event.summary}
                      </p>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <p className="rounded-lg border border-border/60 bg-background/50 p-3 text-2xs leading-relaxed text-muted-foreground">
          {t("activity.note")}
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
