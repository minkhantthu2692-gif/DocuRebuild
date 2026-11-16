import { CircleAlert } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import type { TableProposalCell } from "@docurebuild/shared-types";

import { Badge } from "@/components/ui/badge";
import { needsTableAcknowledgement, type TableGridProposal } from "@/lib/table-candidates";
import { cn } from "@/lib/utils";

/**
 * The reviewable part of a table proposal. Both the single-block dialog and the
 * page-level candidate dialog show exactly this grid, so a cell is never
 * presented differently depending on where the proposal came from.
 */
interface TableReviewProps {
  proposal: TableGridProposal;
  headerRow: boolean;
  onHeaderRowChange: (checked: boolean) => void;
  acknowledged: boolean;
  onAcknowledgedChange: (checked: boolean) => void;
}

export function TableReview({
  proposal,
  headerRow,
  onHeaderRowChange,
  acknowledged,
  onAcknowledgedChange,
}: TableReviewProps) {
  const { t } = useTranslation("workspace");
  const needsReview = needsTableAcknowledgement(proposal);

  const matrix = useMemo(() => {
    const rows = Array.from({ length: proposal.rows }, () =>
      Array.from({ length: proposal.columns }, () => null as TableProposalCell | null),
    );
    for (const cell of proposal.cells) {
      if (rows[cell.row]?.[cell.column] !== undefined) {
        rows[cell.row][cell.column] = cell;
      }
    }
    return rows;
  }, [proposal]);

  return (
    <>
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="outline">
          {t("ocr.table.rowsColumns", {
            rows: proposal.rows,
            columns: proposal.columns,
          })}
        </Badge>
        {proposal.uncertain_cells > 0 ? (
          <Badge variant="warning">
            {t("ocr.table.uncertain", { count: proposal.uncertain_cells })}
          </Badge>
        ) : null}
        {proposal.empty_cells > 0 ? (
          <Badge variant="outline">
            {t("ocr.table.empty", { count: proposal.empty_cells })}
          </Badge>
        ) : null}
      </div>

      {proposal.warnings.includes("no_confidence") ? (
        <p className="flex gap-2 rounded-lg border border-border/60 bg-background/50 p-3 text-2xs leading-relaxed text-muted-foreground">
          <CircleAlert
            className="mt-0.5 size-icon-sm shrink-0 text-warning"
            aria-hidden="true"
          />
          <span>{t("ocr.table.noConfidence")}</span>
        </p>
      ) : proposal.uncertain_cells > 0 ? (
        <p className="flex gap-2 rounded-lg border border-warning/40 bg-warning/10 p-3 text-2xs leading-relaxed text-muted-foreground">
          <CircleAlert
            className="mt-0.5 size-icon-sm shrink-0 text-warning"
            aria-hidden="true"
          />
          <span>{t("ocr.table.lowConfidence")}</span>
        </p>
      ) : null}

      <div className="scrollbar-thin min-h-0 flex-1 overflow-auto rounded-lg border border-border/70 bg-background/40">
        <table className="w-full border-collapse text-xs">
          <tbody>
            {matrix.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, columnIndex) => {
                  const isHeader = headerRow && rowIndex === 0;
                  const confidence =
                    cell?.confidence === null || cell?.confidence === undefined
                      ? null
                      : Math.round(cell.confidence);
                  const title = cell?.uncertain
                    ? t("ocr.table.uncertainCell")
                    : confidence !== null
                      ? t("ocr.table.confidence", { value: confidence })
                      : undefined;
                  const className = cn(
                    "min-w-20 border border-border/60 px-2 py-1.5 align-top font-document leading-relaxed",
                    isHeader && "bg-muted/40 font-semibold",
                    cell?.uncertain && "bg-warning/10",
                    cell?.empty && "bg-muted/20",
                  );
                  const content = (
                    <span className="flex items-start gap-1">
                      {cell?.uncertain ? (
                        <CircleAlert
                          className="mt-0.5 size-3 shrink-0 text-warning"
                          aria-hidden="true"
                        />
                      ) : null}
                      {cell?.text ? (
                        <span className="whitespace-pre-wrap break-words">
                          {cell.text}
                        </span>
                      ) : (
                        <span className="sr-only">{t("ocr.table.emptyCell")}</span>
                      )}
                    </span>
                  );
                  return isHeader ? (
                    <th key={columnIndex} scope="col" title={title} className={className}>
                      {content}
                    </th>
                  ) : (
                    <td key={columnIndex} title={title} className={className}>
                      {content}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="space-y-2 rounded-lg border border-border/60 bg-background/45 p-3">
        <label className="flex items-center gap-2 text-2xs text-muted-foreground">
          <input
            type="checkbox"
            className="size-3.5 accent-primary"
            checked={headerRow}
            onChange={(event) => onHeaderRowChange(event.target.checked)}
          />
          {t("ocr.table.headerRow")}
        </label>
        {needsReview ? (
          <label className="flex items-start gap-2 text-2xs text-muted-foreground">
            <input
              type="checkbox"
              className="mt-0.5 size-3.5 accent-primary"
              checked={acknowledged}
              onChange={(event) => onAcknowledgedChange(event.target.checked)}
            />
            {t("ocr.table.acknowledge")}
          </label>
        ) : null}
      </div>
    </>
  );
}
