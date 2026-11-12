import { CircleAlert } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { Spinner } from "@/components/ui/spinner";
import { useDocumentRevision } from "@/hooks/use-document";
import { diffText } from "@/lib/text-diff";
import { cn } from "@/lib/utils";

interface RevisionCompareProps {
  projectId: string;
  revisionId: string;
  /** Live editor text, including changes that are not saved yet. */
  currentText: string;
}

/**
 * Read-only line comparison between a stored version and what is on screen.
 * Nothing is saved or replaced here; restoring stays a separate action.
 */
export function RevisionCompare({
  projectId,
  revisionId,
  currentText,
}: RevisionCompareProps) {
  const { t } = useTranslation("workspace");
  const query = useDocumentRevision(projectId, revisionId);

  const diff = useMemo(
    () => (query.data ? diffText(query.data.plain_text, currentText) : null),
    [query.data, currentText],
  );

  return (
    <div className="mt-2 rounded-md border border-border/60 bg-background/60 p-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <p className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
          {t("revisions.compareTitle")}
        </p>
        {diff && !diff.identical && !diff.tooLarge ? (
          <p className="ml-auto flex flex-wrap items-center gap-2 text-2xs">
            <span className="text-success">
              {t("revisions.compareAdded", { count: diff.added })}
            </span>
            <span className="text-warning">
              {t("revisions.compareRemoved", { count: diff.removed })}
            </span>
          </p>
        ) : null}
      </div>

      {query.isLoading ? (
        <p className="mt-1 flex items-center gap-1.5 text-2xs text-muted-foreground">
          <Spinner className="size-icon-sm" />
          {t("revisions.compareLoading")}
        </p>
      ) : query.isError ? (
        <p className="mt-1 flex items-start gap-1.5 text-2xs text-warning">
          <CircleAlert className="mt-0.5 size-icon-sm shrink-0" aria-hidden="true" />
          {t("revisions.compareError")}
        </p>
      ) : diff?.identical ? (
        <p className="mt-1 text-2xs leading-relaxed text-muted-foreground">
          {t("revisions.compareIdentical")}
        </p>
      ) : diff?.tooLarge ? (
        <p className="mt-1 text-2xs leading-relaxed text-muted-foreground">
          {t("revisions.compareTooLarge")}
        </p>
      ) : diff ? (
        <>
          <ul className="mt-2 max-h-56 space-y-px overflow-y-auto font-mono text-2xs leading-relaxed">
            {diff.rows.map((row, index) => {
              if (row.kind === "gap") {
                return (
                  <li
                    key={`gap-${index}`}
                    className="rounded-xs px-1.5 py-1 text-center text-2xs text-muted-foreground"
                  >
                    {t("revisions.compareGap", { count: row.count })}
                  </li>
                );
              }

              const added = row.kind === "added";
              const removed = row.kind === "removed";
              const blank = row.text.trim().length === 0;
              return (
                <li
                  key={`line-${index}`}
                  className={cn(
                    "flex gap-1.5 whitespace-pre-wrap break-words rounded-xs px-1.5 py-0.5",
                    added && "bg-success/10 text-success",
                    removed && "bg-warning/10 text-warning",
                    !added && !removed && "text-muted-foreground",
                  )}
                >
                  <span aria-hidden="true" className="select-none">
                    {added ? "+" : removed ? "−" : " "}
                  </span>
                  <span className={cn(blank && "italic opacity-70")}>
                    {blank ? t("revisions.compareBlankLine") : row.text}
                  </span>
                  {added || removed ? (
                    <span className="sr-only">
                      {added
                        ? t("revisions.compareAddedLine")
                        : t("revisions.compareRemovedLine")}
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
          <p className="mt-2 text-2xs leading-relaxed text-muted-foreground">
            {t("revisions.compareHint")}
          </p>
        </>
      ) : null}
    </div>
  );
}
