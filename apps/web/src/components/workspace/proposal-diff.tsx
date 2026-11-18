import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { diffInlineText } from "@/lib/text-diff";
import { cn } from "@/lib/utils";

interface ProposalDiffProps {
  original: string;
  proposed: string;
  originalLabel: string;
  proposedLabel: string;
  /** Render with the document typeface, like the OCR review dialog. */
  documentFont?: boolean;
  /** Draw the proposal as a quiet, already-decided entry. */
  mutedProposed?: boolean;
}

/**
 * Side-by-side original and proposed text with the changed characters marked.
 *
 * The comparison is local and read-only. Removed text uses `<del>` and added text
 * uses `<ins>`, so the difference is conveyed by the element itself, not by colour
 * alone. Nothing here can accept a proposal or change the document.
 */
export function ProposalDiff({
  original,
  proposed,
  originalLabel,
  proposedLabel,
  documentFont = false,
  mutedProposed = false,
}: ProposalDiffProps) {
  const { t } = useTranslation("workspace");
  const diff = useMemo(() => diffInlineText(original, proposed), [original, proposed]);
  const textClass = cn(
    "mt-1 whitespace-pre-wrap break-words text-xs leading-relaxed",
    documentFont && "font-document",
  );

  return (
    <div className="grid gap-2 sm:grid-cols-2">
      <div className="min-w-0 rounded-md border border-border/60 bg-background/60 p-2">
        <p className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
          {originalLabel}
        </p>
        <p dir="auto" className={textClass}>
          {diff.segments.map((segment, index) =>
            segment.kind === "added" ? null : segment.kind === "removed" ? (
              <del
                key={index}
                className="rounded-xs bg-destructive/10 text-destructive line-through decoration-destructive/60"
              >
                {segment.text}
              </del>
            ) : (
              <span key={index}>{segment.text}</span>
            ),
          )}
        </p>
      </div>
      <div
        className={cn(
          "min-w-0 rounded-md border bg-background/60 p-2",
          mutedProposed ? "border-border/60" : "border-primary/30",
        )}
      >
        <p
          className={cn(
            "text-2xs font-semibold uppercase tracking-wider",
            mutedProposed ? "text-muted-foreground" : "text-primary",
          )}
        >
          {proposedLabel}
        </p>
        <p dir="auto" className={textClass}>
          {diff.segments.map((segment, index) =>
            segment.kind === "removed" ? null : segment.kind === "added" ? (
              <ins
                key={index}
                className="rounded-xs bg-success/10 text-success underline decoration-success/60 underline-offset-2"
              >
                {segment.text}
              </ins>
            ) : (
              <span key={index}>{segment.text}</span>
            ),
          )}
        </p>
      </div>
      {diff.identical ? null : (
        <p className="text-2xs leading-relaxed text-muted-foreground sm:col-span-2">
          {t(diff.coarse ? "ocr.ai.diffCoarse" : "ocr.ai.diffLegend")}
        </p>
      )}
    </div>
  );
}
