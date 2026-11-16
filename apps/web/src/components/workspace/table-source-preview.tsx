import { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  sourceCropGeometry,
  type TableGridProposal,
} from "@/lib/table-candidates";

/** Tallest the crop preview may get, expressed in rem. */
const PREVIEW_MAX_REM = 14;
/** Breathing room around the exact word box, in page pixels. */
const PREVIEW_PADDING = 10;

interface TableSourcePreviewProps {
  proposal: TableGridProposal;
  pageWidth: number | null;
  pageHeight: number | null;
  imageUrl: string;
}

/**
 * Crop of the page region the proposal was read from, shown beside the grid so
 * the user can compare cells with the source. The image is positioned by
 * percentage, so no measuring or resize observer is needed.
 */
export function TableSourcePreview({
  proposal,
  pageWidth,
  pageHeight,
  imageUrl,
}: TableSourcePreviewProps) {
  const { t } = useTranslation("workspace");
  const [failed, setFailed] = useState(false);
  const box = proposal.source;
  const geometry = sourceCropGeometry(
    {
      x: box.x - PREVIEW_PADDING,
      y: box.y - PREVIEW_PADDING,
      width: box.width + PREVIEW_PADDING * 2,
      height: box.height + PREVIEW_PADDING * 2,
    },
    pageWidth,
    pageHeight,
  );

  if (!geometry) {
    return null;
  }

  if (failed) {
    return (
      <p className="rounded-lg border border-border/60 bg-background/45 p-3 text-2xs text-muted-foreground">
        {t("ocr.table.sourceUnavailable")}
      </p>
    );
  }

  return (
    <figure className="space-y-1">
      <div
        className="relative mx-auto overflow-hidden rounded-lg border border-border/70 bg-muted/20"
        style={{
          aspectRatio: geometry.aspectRatio,
          width: `min(100%, ${(geometry.aspectRatio * PREVIEW_MAX_REM).toFixed(2)}rem)`,
        }}
      >
        <img
          src={imageUrl}
          alt=""
          aria-hidden="true"
          className="absolute max-w-none select-none"
          style={{
            left: `${geometry.image.left}%`,
            top: `${geometry.image.top}%`,
            width: `${geometry.image.width}%`,
            height: `${geometry.image.height}%`,
          }}
          onError={() => setFailed(true)}
        />
      </div>
      <figcaption className="text-center text-2xs text-muted-foreground">
        {t("ocr.table.sourceRegion")}
      </figcaption>
    </figure>
  );
}
