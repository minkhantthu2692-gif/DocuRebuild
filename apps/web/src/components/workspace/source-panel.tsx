import {
  ArrowLeft,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  Image as ImageIcon,
  Images,
  Layers,
  Maximize2,
  MoreHorizontal,
  RotateCcw,
  RotateCw,
  ScanSearch,
  ScanText,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Undo2,
  Upload,
  WandSparkles,
  X,
  ZoomIn,
  ZoomOut,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";

import type {
  ImportJob,
  OcrBlockKind,
  PageSummary,
  RegionProposal,
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/ui/empty-state";
import { Spinner } from "@/components/ui/spinner";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useAiRegionProposals } from "@/hooks/use-ai";
import { useAppMeta } from "@/hooks/use-app";
import { useElements, useRegionProposals } from "@/hooks/use-elements";
import { useLatestOcr } from "@/hooks/use-ocr";
import {
  useCancelImportJob,
  useDeletePage,
  useImportJob,
  useImportJobs,
  usePages,
  useReorderPages,
  useRotatePage,
  useStartImport,
} from "@/hooks/use-projects";
import { api } from "@/lib/api";
import {
  displayRect,
  selectionToSourceRect,
  type DisplayPoint,
  type SourceRect,
} from "@/lib/element-region";
import {
  IMAGE_ACCEPT_ATTRIBUTE,
  IMPORT_ACCEPT_ATTRIBUTE,
  partitionImportFiles,
} from "@/lib/import-files";
import { containFrame, layoutBoxes, layoutRect, type ImageFrame } from "@/lib/layout-overlay";
import { cn } from "@/lib/utils";
import { OcrDialog } from "./ocr-dialog";
import { EditsDialog } from "./edits-dialog";
import { ElementsDialog } from "./elements-dialog";

interface SourcePanelProps {
  projectId: string;
  className?: string;
  onContentInserted?: () => void;
}

type ViewScale =
  | { kind: "fit" }
  | { kind: "actual" }
  | { kind: "zoom"; value: number };

const MIN_ZOOM = 0.25;
const MAX_ZOOM = 4;

const ACTIVE_IMPORT_STATUSES: ReadonlySet<ImportJob["status"]> = new Set([
  "queued",
  "running",
  "cancelling",
]);

const LAYOUT_KIND_ORDER: readonly OcrBlockKind[] = [
  "heading",
  "paragraph",
  "list_item",
  "table",
  "equation",
  "caption",
  "header",
  "footer",
  "page_number",
];

const LAYOUT_BOX_CLASS: Record<OcrBlockKind, string> = {
  heading: "border-primary/80 bg-primary/10",
  paragraph: "border-muted-foreground/50 bg-muted-foreground/5",
  list_item: "border-info/70 bg-info/10",
  table: "border-info/80 border-dashed bg-info/10",
  equation: "border-warning/80 bg-warning/10",
  caption: "border-success/70 bg-success/10",
  header: "border-muted-foreground/50 bg-transparent",
  footer: "border-muted-foreground/40 bg-transparent",
  page_number: "border-muted-foreground/30 border-dashed bg-transparent",
};

const LAYOUT_SWATCH_CLASS: Record<OcrBlockKind, string> = {
  heading: "bg-primary",
  paragraph: "bg-muted-foreground/60",
  list_item: "bg-info",
  table: "bg-info/60",
  equation: "bg-warning",
  caption: "bg-success",
  header: "bg-muted-foreground/50",
  footer: "bg-muted-foreground/40",
  page_number: "bg-muted-foreground/30",
};

function sameFrame(current: ImageFrame | null, next: ImageFrame | null): boolean {
  if (current === next) return true;
  if (!current || !next) return false;
  return (Object.keys(current) as (keyof ImageFrame)[]).every(
    (key) => Math.abs(current[key] - next[key]) < 0.5,
  );
}

function hasFiles(event: { dataTransfer: DataTransfer | null }): boolean {
  return Boolean(event.dataTransfer && Array.from(event.dataTransfer.types).includes("Files"));
}

interface ToolButtonProps {
  label: string;
  icon: LucideIcon;
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
  className?: string;
}

function ToolButton({
  label,
  icon: Icon,
  onClick,
  disabled,
  active,
  className,
}: ToolButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant={active ? "secondary" : "ghost"}
          size="icon-xs"
          aria-label={label}
          aria-pressed={active}
          disabled={disabled}
          onClick={onClick}
          className={className}
        >
          <Icon />
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

interface PageThumbnailsProps {
  pages: PageSummary[];
  projectId: string;
  selectedId: string | null;
  onSelect: (pageId: string) => void;
  onMove: (pageId: string, targetId: string) => void;
  labelFor: (page: PageSummary) => string;
  groupLabel: string;
}

function PageThumbnails({
  pages,
  projectId,
  selectedId,
  onSelect,
  onMove,
  labelFor,
  groupLabel,
}: PageThumbnailsProps) {
  const [draggingId, setDraggingId] = useState<string | null>(null);

  return (
    <div
      aria-label={groupLabel}
      className="scrollbar-thin flex shrink-0 flex-row gap-2 overflow-x-auto border-t border-border/60 bg-background/30 p-2 sm:w-20 sm:flex-col sm:overflow-y-auto sm:overflow-x-hidden sm:border-r sm:border-t-0"
    >
      {pages.map((page) => {
        const selected = page.id === selectedId;
        return (
          <button
            key={page.id}
            type="button"
            draggable
            aria-current={selected ? "true" : undefined}
            aria-label={labelFor(page)}
            title={labelFor(page)}
            onClick={() => onSelect(page.id)}
            onDragStart={(event) => {
              event.dataTransfer.effectAllowed = "move";
              event.dataTransfer.setData("text/plain", page.id);
              setDraggingId(page.id);
            }}
            onDragEnd={() => setDraggingId(null)}
            onDragOver={(event) => {
              if (!draggingId) return;
              event.preventDefault();
              event.dataTransfer.dropEffect = "move";
            }}
            onDrop={(event) => {
              if (!draggingId) return;
              event.preventDefault();
              event.stopPropagation();
              onMove(draggingId, page.id);
              setDraggingId(null);
            }}
            className={cn(
              "focus-ring group relative h-16 w-12 shrink-0 overflow-hidden rounded-md border bg-card/80 transition-all duration-base sm:h-auto sm:w-full",
              selected
                ? "border-primary ring-2 ring-primary/35"
                : "border-border/70 hover:border-primary/40",
              draggingId === page.id && "opacity-40",
            )}
          >
            <img
              src={api.assetUrl(projectId, page.thumbnail_asset_id, page.updated_at) ?? ""}
              alt=""
              loading="lazy"
              draggable={false}
              className="aspect-[3/4] h-full w-full object-cover"
            />
            <span className="absolute bottom-0 left-0 right-0 bg-foreground/60 px-1 py-0.5 text-center font-mono text-2xs leading-tight text-background">
              {page.page_number}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function SourcePanel({ projectId, className, onContentInserted }: SourcePanelProps) {
  const { t } = useTranslation("workspace");
  const { t: tCommon } = useTranslation("common");
  const { t: tError, i18n } = useTranslation("errors");
  const queryClient = useQueryClient();
  const pagesQuery = usePages(projectId);
  const metaQuery = useAppMeta();
  const pages = useMemo(() => pagesQuery.data ?? [], [pagesQuery.data]);
  const meta = metaQuery.data;

  const startImport = useStartImport(projectId);
  const cancelImport = useCancelImportJob(projectId);
  const importJobsQuery = useImportJobs(projectId);
  const rotatePage = useRotatePage(projectId);
  const deletePage = useDeletePage(projectId);
  const reorderPages = useReorderPages(projectId);
  const errorMessage = useApiErrorMessage();

  const [importJobId, setImportJobId] = useState<string | null>(null);
  const importJobQuery = useImportJob(projectId, importJobId);
  const importJob = importJobQuery.data ?? null;
  const importActive =
    startImport.isPending ||
    Boolean(importJob && ACTIVE_IMPORT_STATUSES.has(importJob.status));

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [scale, setScale] = useState<ViewScale>({ kind: "fit" });
  const [dragging, setDragging] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<PageSummary | null>(null);
  const [ocrOpen, setOcrOpen] = useState(false);
  const [editsOpen, setEditsOpen] = useState(false);
  const [elementsOpen, setElementsOpen] = useState(false);
  const [selectMode, setSelectMode] = useState(false);
  const [pendingSelection, setPendingSelection] = useState<SourceRect | null>(null);
  const [proposalsOn, setProposalsOn] = useState(false);
  const [pendingProposal, setPendingProposal] = useState<RegionProposal | null>(null);
  const [dragStart, setDragStart] = useState<DisplayPoint | null>(null);
  const [dragCurrent, setDragCurrent] = useState<DisplayPoint | null>(null);
  const [overlayOn, setOverlayOn] = useState(false);
  const [imageFrame, setImageFrame] = useState<ImageFrame | null>(null);
  const dragDepth = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const activeFrameRef = useRef<ImageFrame | null>(null);
  const handledJobRef = useRef<string | null>(null);
  const resumeCheckedRef = useRef(false);

  // Reattach to an import that was already running when the workspace loaded.
  useEffect(() => {
    if (resumeCheckedRef.current) return;
    if (importJobId) {
      resumeCheckedRef.current = true;
      return;
    }
    if (!importJobsQuery.data) return;
    resumeCheckedRef.current = true;
    const active = importJobsQuery.data.find((job) => ACTIVE_IMPORT_STATUSES.has(job.status));
    if (active) {
      setImportJobId(active.id);
    }
  }, [importJobId, importJobsQuery.data]);

  // Report the final outcome once, then stop polling. Pages are refreshed only
  // after the job settles so a cancelled import never leaves thumbnails that
  // point at files the backend has already rolled back.
  useEffect(() => {
    if (!importJob || ACTIVE_IMPORT_STATUSES.has(importJob.status)) return;
    if (handledJobRef.current === importJob.id) return;
    handledJobRef.current = importJob.id;

    void queryClient.invalidateQueries({ queryKey: ["pages", projectId] });
    void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    void queryClient.invalidateQueries({ queryKey: ["projects"] });
    void queryClient.invalidateQueries({ queryKey: ["import-jobs", projectId] });

    if (importJob.status === "succeeded") {
      toast.success(t("importSuccess", { count: importJob.imported_pages }));
    } else if (importJob.status === "cancelled") {
      toast.info(t("importProgress.cancelled", { count: importJob.imported_pages }));
    } else {
      const code = importJob.error_code;
      toast.error(
        code && i18n.exists(code, { ns: "errors" }) ? tError(code) : tError("generic"),
      );
    }
    setImportJobId(null);
  }, [importJob, projectId, queryClient, t, tError, i18n]);

  const selectedIndex = pages.findIndex((page) => page.id === selectedId);
  const currentPage = selectedIndex >= 0 ? pages[selectedIndex] : (pages[0] ?? null);

  // Vision proposals are never saved; this mutation only feeds the overlay.
  const aiRegions = useAiRegionProposals(projectId, currentPage?.id ?? null);
  const aiRegionData = aiRegions.data ?? null;
  const resetAiRegions = aiRegions.reset;

  useEffect(() => {
    if (pages.length === 0) {
      if (selectedId !== null) setSelectedId(null);
      return;
    }
    if (!selectedId || !pages.some((page) => page.id === selectedId)) {
      setSelectedId(pages[0].id);
    }
  }, [pages, selectedId]);

  useEffect(() => {
    setScale({ kind: "fit" });
  }, [currentPage?.id]);

  // Cancel an unfinished marquee whenever the page changes; coordinates from
  // one page must never be applied to another.
  useEffect(() => {
    setSelectMode(false);
    setDragStart(null);
    setDragCurrent(null);
    setPendingSelection(null);
    setProposalsOn(false);
    setPendingProposal(null);
    activeFrameRef.current = null;
    resetAiRegions();
  }, [currentPage?.id, resetAiRegions]);

  const elementsQuery = useElements(projectId, currentPage?.id ?? null);
  const elementCount = elementsQuery.data?.length ?? 0;
  const proposalsQuery = useRegionProposals(
    projectId,
    currentPage?.id ?? null,
    proposalsOn,
  );

  // The overlay loads the latest OCR run only when the user turns it on, so a
  // page viewer without OCR does not poll the API.
  const latestOcrQuery = useLatestOcr(projectId, currentPage?.id ?? null, overlayOn);
  const latestOcr = latestOcrQuery.data ?? null;

  const maxBytes = useMemo(
    () => (meta ? meta.max_import_mb * 1024 * 1024 : null),
    [meta],
  );
  const allowPdf = meta?.capabilities.import_pdf ?? false;

  const pointInContent = (
    event: ReactPointerEvent<HTMLDivElement>,
  ): DisplayPoint | null => {
    const container = contentRef.current;
    if (!container) return null;
    const bounds = container.getBoundingClientRect();
    return { x: event.clientX - bounds.left, y: event.clientY - bounds.top };
  };

  const clampToFrame = (point: DisplayPoint, frame: ImageFrame): DisplayPoint => ({
    x: Math.min(Math.max(point.x, frame.left), frame.left + frame.width),
    y: Math.min(Math.max(point.y, frame.top), frame.top + frame.height),
  });

  const cancelRegionSelect = useCallback(() => {
    setSelectMode(false);
    setDragStart(null);
    setDragCurrent(null);
    activeFrameRef.current = null;
  }, []);

  const abortDrag = () => {
    setDragStart(null);
    setDragCurrent(null);
    activeFrameRef.current = null;
  };

  const consumePendingSelection = useCallback(() => {
    setPendingSelection(null);
  }, []);

  const consumePendingProposal = useCallback(() => {
    setPendingProposal(null);
  }, []);

  const requestAiRegions = () => {
    if (!currentPage || aiRegions.isPending) return;
    cancelRegionSelect();
    setProposalsOn(false);
    aiRegions.mutate(
      {},
      {
        onSuccess: (result) => {
          if (result.proposals.length === 0) {
            toast.info(t("elements.ai.empty"));
          }
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  };

  const applyProposal = (proposal: RegionProposal) => {
    setSelectMode(false);
    setDragStart(null);
    setDragCurrent(null);
    setPendingSelection(null);
    setProposalsOn(false);
    resetAiRegions();
    setPendingProposal(proposal);
    setElementsOpen(true);
  };

  const handleElementsOpenChange = (open: boolean) => {
    setElementsOpen(open);
    if (!open) {
      setSelectMode(false);
      setDragStart(null);
      setDragCurrent(null);
      setPendingProposal(null);
      activeFrameRef.current = null;
    }
  };

  const beginRegionSelect = () => {
    if (!currentPage) return;
    setElementsOpen(false);
    setProposalsOn(false);
    resetAiRegions();
    setSelectMode(true);
    setDragStart(null);
    setDragCurrent(null);
    activeFrameRef.current = null;
  };

  const handleSelectStart = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!selectMode) return;
    const point = pointInContent(event);
    if (!point) return;
    // Measure at pointer time: on a freshly opened page the frame may not have
    // reached React state yet, and a stale frame must never start a selection.
    const frame = measureImage();
    if (!frame) return;
    if (
      point.x < frame.left ||
      point.x > frame.left + frame.width ||
      point.y < frame.top ||
      point.y > frame.top + frame.height
    ) {
      return;
    }
    event.preventDefault();
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // Pointer capture is best-effort. Some environments reject it for
      // pointers the browser does not consider active; the drag still works
      // while the pointer stays inside the viewer.
    }
    activeFrameRef.current = frame;
    const start = clampToFrame(point, frame);
    setDragStart(start);
    setDragCurrent(start);
  };

  const handleSelectMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const frame = activeFrameRef.current;
    if (!dragStart || !frame) return;
    const point = pointInContent(event);
    if (!point) return;
    setDragCurrent(clampToFrame(point, frame));
  };

  const handleSelectEnd = (event: ReactPointerEvent<HTMLDivElement>) => {
    const frame = activeFrameRef.current;
    if (!dragStart || !frame) return;
    const point = pointInContent(event);
    const end = point ? clampToFrame(point, frame) : (dragCurrent ?? dragStart);
    const region = selectionToSourceRect(dragStart, end, frame);
    setDragStart(null);
    setDragCurrent(null);
    activeFrameRef.current = null;
    if (!region) {
      toast.error(t("elements.errors.invalidRegion"));
      return;
    }
    setSelectMode(false);
    setPendingSelection(region);
    setElementsOpen(true);
  };

  useEffect(() => {
    if (!selectMode) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") cancelRegionSelect();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectMode, cancelRegionSelect]);

  const handleFiles = (files: FileList | File[]) => {
    const list = Array.from(files);
    if (list.length === 0 || importActive) return;

    const { accepted, rejected } = partitionImportFiles(list, maxBytes, allowPdf);
    rejected.slice(0, 3).forEach(({ file, reason }) => {
      toast.error(
        t(reason === "unsupported" ? "importErrors.unsupported" : "importErrors.tooLarge", {
          name: file.name,
          size: meta?.max_import_mb ?? "",
        }),
      );
    });
    if (rejected.length > 3) {
      toast.error(t("importErrors.moreRejected", { count: rejected.length - 3 }));
    }

    if (accepted.length === 0) {
      if (rejected.length === 0) toast.error(t("importErrors.noneAccepted"));
      return;
    }
    if (meta && accepted.length > meta.max_upload_batch) {
      toast.error(t("importErrors.tooMany", { count: meta.max_upload_batch }));
      return;
    }

    handledJobRef.current = null;
    startImport.mutate(accepted, {
      onSuccess: (job) => setImportJobId(job.id),
      onError: (error) => toast.error(errorMessage(error)),
    });
  };

  const requestCancelImport = () => {
    if (!importJob || importJob.status === "cancelling") return;
    cancelImport.mutate(importJob.id, {
      onError: (error) => toast.error(errorMessage(error)),
    });
  };

  const movePage = (fromId: string, targetId: string) => {
    if (!pages.length || fromId === targetId) return;
    const ids = pages.map((page) => page.id);
    const from = ids.indexOf(fromId);
    const to = ids.indexOf(targetId);
    if (from < 0 || to < 0) return;
    ids.splice(to, 0, ids.splice(from, 1)[0]);
    reorderPages.mutate(ids, { onError: (error) => toast.error(errorMessage(error)) });
  };

  const moveBy = (delta: number) => {
    if (!currentPage) return;
    const index = pages.findIndex((page) => page.id === currentPage.id);
    const target = pages[index + delta];
    if (target) movePage(currentPage.id, target.id);
  };

  const rotate = (degrees: number) => {
    if (!currentPage) return;
    // A rotated page image no longer matches proposals derived from the old one.
    resetAiRegions();
    setProposalsOn(false);
    rotatePage.mutate(
      { pageId: currentPage.id, degrees },
      { onError: (error) => toast.error(errorMessage(error)) },
    );
  };

  const zoomBy = (factor: number) => {
    setScale((current) => {
      const base = current.kind === "zoom" ? current.value : 1;
      return {
        kind: "zoom",
        value: Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, base * factor)),
      };
    });
  };

  const labelFor = (page: PageSummary) =>
    t("viewer.pageOf", { page: page.page_number, total: pages.length });

  const zoomPercent =
    scale.kind === "fit" ? null : scale.kind === "actual" ? 100 : Math.round(scale.value * 100);

  const importPercent = importJob
    ? Math.round(Math.min(1, Math.max(0, importJob.progress)) * 100)
    : 0;

  const imageStyle =
    currentPage && scale.kind !== "fit"
      ? {
          width:
            scale.kind === "actual"
              ? (currentPage.width ?? undefined)
              : `${scale.value * 100}%`,
        }
      : undefined;

  const imageSrc = currentPage
    ? api.assetUrl(
        projectId,
        currentPage.display_asset_id ?? currentPage.original_asset_id,
        currentPage.updated_at,
      )
    : null;

  const measureImage = useCallback((): ImageFrame | null => {
    const image = imageRef.current;
    const container = contentRef.current;
    if (!image || !container) {
      setImageFrame(null);
      return null;
    }
    // Measure against the marquee container using viewport coordinates so the
    // frame stays correct while the viewer is scrolled.
    const imageRect = image.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    const next = containFrame(
      {
        left: imageRect.left - containerRect.left,
        top: imageRect.top - containerRect.top,
        width: image.clientWidth,
        height: image.clientHeight,
      },
      image.naturalWidth,
      image.naturalHeight,
    );
    setImageFrame((current) => (sameFrame(current, next) ? current : next));
    return next;
  }, []);

  useEffect(() => {
    if (!overlayOn && !selectMode && !proposalsOn) {
      setImageFrame(null);
      return;
    }
    measureImage();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => measureImage());
    if (imageRef.current) observer.observe(imageRef.current);
    if (viewportRef.current) observer.observe(viewportRef.current);
    return () => observer.disconnect();
  }, [measureImage, overlayOn, selectMode, proposalsOn, imageSrc]);

  const overlayBoxes = useMemo(() => {
    if (!overlayOn || !imageFrame || !latestOcr) return [];
    if (latestOcr.status !== "succeeded" || latestOcr.stale) return [];
    return layoutBoxes(latestOcr.blocks, imageFrame);
  }, [overlayOn, imageFrame, latestOcr]);

  const overlayLegend = useMemo(() => {
    const counts = new Map<OcrBlockKind, number>();
    overlayBoxes.forEach((box) => counts.set(box.kind, (counts.get(box.kind) ?? 0) + 1));
    return LAYOUT_KIND_ORDER.filter((kind) => counts.has(kind)).map((kind) => ({
      kind,
      count: counts.get(kind) ?? 0,
    }));
  }, [overlayBoxes]);

  const aiProposals = aiRegionData?.proposals ?? null;
  const proposalBoxes = useMemo(() => {
    const proposals = aiProposals
      ? aiProposals
      : proposalsOn && proposalsQuery.data?.status === "ready"
        ? proposalsQuery.data.proposals
        : null;
    if (!imageFrame || !proposals) return [];
    return proposals.flatMap((proposal) => {
      const box = layoutRect(proposal, imageFrame);
      return box ? [{ proposal, box }] : [];
    });
  }, [aiProposals, proposalsOn, imageFrame, proposalsQuery.data]);

  let overlayMessage: string | null = null;
  if (overlayOn) {
    if (latestOcrQuery.isLoading) overlayMessage = "viewer.overlay.loading";
    else if (latestOcrQuery.isError) overlayMessage = "viewer.overlay.error";
    else if (!latestOcr) overlayMessage = "viewer.overlay.empty";
    else if (latestOcr.status === "failed") overlayMessage = "viewer.overlay.failed";
    else if (latestOcr.status === "queued" || latestOcr.status === "running") {
      overlayMessage = "viewer.overlay.running";
    } else if (latestOcr.stale) overlayMessage = "viewer.overlay.stale";
    else if (overlayBoxes.length === 0) overlayMessage = "viewer.overlay.empty";
  }

  let proposalMessage: string | null = null;
  if (proposalsOn) {
    const status = proposalsQuery.data?.status;
    if (proposalsQuery.isLoading) proposalMessage = "elements.proposals.loading";
    else if (proposalsQuery.isError) proposalMessage = "elements.proposals.error";
    else if (!status) proposalMessage = "elements.proposals.loading";
    else if (status !== "ready") {
      proposalMessage = `elements.proposals.status.${status}`;
    } else if (proposalBoxes.length === 0) {
      proposalMessage = "elements.proposals.empty";
    }
  }

  return (
    <section
      aria-label={t("source")}
      className={cn(
        "relative flex h-full min-h-0 flex-col bg-background/20",
        dragging && "ring-2 ring-inset ring-primary/40",
        className,
      )}
      onDragEnter={(event) => {
        if (!hasFiles(event)) return;
        event.preventDefault();
        dragDepth.current += 1;
        setDragging(true);
      }}
      onDragOver={(event) => {
        if (!hasFiles(event)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
      }}
      onDragLeave={(event) => {
        if (!hasFiles(event)) return;
        dragDepth.current = Math.max(0, dragDepth.current - 1);
        if (dragDepth.current === 0) setDragging(false);
      }}
      onDrop={(event) => {
        if (!hasFiles(event)) return;
        event.preventDefault();
        dragDepth.current = 0;
        setDragging(false);
        handleFiles(event.dataTransfer.files);
      }}
    >
      <header className="flex h-panel shrink-0 items-center gap-2 border-b border-border/60 bg-background/35 px-3">
        <ImageIcon className="size-icon-sm text-muted-foreground" aria-hidden="true" />
        <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {t("source")}
        </h2>
        {pages.length > 0 ? (
          <Badge variant="secondary" className="font-mono">
            {pages.length}
          </Badge>
        ) : null}
        {startImport.isPending ? (
          <span className="ml-1 flex items-center gap-1.5 text-2xs text-muted-foreground">
            <Spinner className="size-3.5" />
            <span className="hidden sm:inline">
              {t("importing", { count: startImport.variables?.length ?? 0 })}
            </span>
          </span>
        ) : null}

        <div className="ml-auto flex items-center gap-0.5">
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5 px-2"
            disabled={importActive}
            onClick={() => inputRef.current?.click()}
          >
            <Upload />
            <span className="hidden sm:inline">{t("importPages")}</span>
            <span className="sr-only sm:hidden">{t("importPages")}</span>
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={tCommon("menu.more")}
                disabled={!currentPage}
              >
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                disabled={!currentPage || selectedIndex <= 0}
                onSelect={() => moveBy(-1)}
              >
                <ArrowLeft />
                <span>{t("viewer.moveLeft")}</span>
              </DropdownMenuItem>
              <DropdownMenuItem
                disabled={!currentPage || selectedIndex >= pages.length - 1}
                onSelect={() => moveBy(1)}
              >
                <ArrowRight />
                <span>{t("viewer.moveRight")}</span>
              </DropdownMenuItem>
              <DropdownMenuItem
                disabled={!currentPage || currentPage.rotation === 0}
                onSelect={() => currentPage && rotate(-currentPage.rotation)}
              >
                <Undo2 />
                <span>{t("viewer.reset")}</span>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                destructive
                disabled={!currentPage}
                onSelect={() => setDeleteTarget(currentPage)}
              >
                <Trash2 />
                <span>{t("viewer.delete")}</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      {importJob && ACTIVE_IMPORT_STATUSES.has(importJob.status) ? (
        <div
          role="status"
          aria-live="polite"
          className="flex shrink-0 items-start gap-3 border-b border-border/60 bg-background/40 px-3 py-2"
        >
          <Spinner className="mt-0.5 size-4 text-primary" />
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate text-xs font-medium">
                {importJob.status === "queued"
                  ? t("importProgress.queued")
                  : importJob.status === "cancelling"
                    ? t("importProgress.cancelling")
                    : t("importProgress.running")}
              </span>
              <span className="shrink-0 font-mono text-2xs text-muted-foreground">
                {t("importProgress.pages", {
                  imported: importJob.imported_pages,
                  total: importJob.total_pages,
                })}
              </span>
            </div>
            <div
              className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted"
              role="progressbar"
              aria-label={t("importProgress.running")}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={importPercent}
            >
              <div
                className="h-full rounded-full bg-primary transition-[width] duration-base"
                style={{ width: `${importPercent}%` }}
              />
            </div>
            {importJob.current_file ? (
              <p className="mt-1 truncate text-2xs text-muted-foreground">
                {t("importProgress.file", { name: importJob.current_file })}
              </p>
            ) : null}
          </div>
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            disabled={importJob.status === "cancelling" || cancelImport.isPending}
            onClick={requestCancelImport}
          >
            <X />
            <span className="hidden sm:inline">{t("importProgress.cancel")}</span>
            <span className="sr-only sm:hidden">{t("importProgress.cancel")}</span>
          </Button>
        </div>
      ) : null}

      <input
        ref={inputRef}
        type="file"
        accept={allowPdf ? IMPORT_ACCEPT_ATTRIBUTE : IMAGE_ACCEPT_ATTRIBUTE}
        multiple
        className="sr-only"
        onChange={(event) => {
          if (event.target.files) handleFiles(event.target.files);
          event.target.value = "";
        }}
      />

      {pagesQuery.isLoading ? (
        <div className="flex flex-1 items-center justify-center">
          <Spinner className="size-icon-lg text-primary" />
          <span className="sr-only">{tCommon("loading")}</span>
        </div>
      ) : null}

      {!pagesQuery.isLoading && pagesQuery.isError ? (
        <div className="flex flex-1 items-center justify-center p-4">
          <EmptyState
            compact
            icon={ImageIcon}
            title={t("sourceLoadError.title")}
            description={t("sourceLoadError.description")}
            action={
              <Button variant="outline" size="sm" onClick={() => void pagesQuery.refetch()}>
                {tCommon("actions.retry")}
              </Button>
            }
          />
        </div>
      ) : null}

      {!pagesQuery.isLoading && !pagesQuery.isError && pages.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 p-4">
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={importActive}
            className="focus-ring group flex w-full max-w-sm flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border/90 bg-background/40 px-6 py-12 text-center transition-colors hover:border-primary/50 hover:bg-primary/5 disabled:pointer-events-none disabled:opacity-60"
          >
            <span className="flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary transition-transform duration-fast group-hover:scale-105">
              {importActive ? <Spinner className="size-icon-lg" /> : <Upload className="size-icon-lg" />}
            </span>
            <span className="space-y-1">
              <span className="block text-sm font-semibold tracking-tight">
                {t(allowPdf ? "dropTitlePdf" : "dropTitle")}
              </span>
              <span className="block text-xs text-muted-foreground">{t("dropHint")}</span>
            </span>
            <span className="text-2xs text-muted-foreground">
              {meta
                ? t(allowPdf ? "supported" : "supportedNoPdf", {
                    size: meta.max_import_mb,
                  })
                : t("supportedNoSize")}
            </span>
          </button>
        </div>
      ) : null}

      {!pagesQuery.isLoading && !pagesQuery.isError && currentPage ? (
        <>
          <div className="flex flex-wrap items-center gap-0.5 border-b border-border/60 bg-background/35 px-2 py-1">
            <ToolButton
              label={t("viewer.previous")}
              icon={ChevronLeft}
              disabled={selectedIndex <= 0}
              onClick={() => setSelectedId(pages[selectedIndex - 1].id)}
            />
            <span className="px-1 font-mono text-2xs text-muted-foreground">
              {t("viewer.pageOf", { page: currentPage.page_number, total: pages.length })}
            </span>
            {currentPage.source_kind === "pdf" && currentPage.pdf_page_number ? (
              <Badge variant="outline" className="font-mono">
                {t("viewer.pdfBadge", { page: currentPage.pdf_page_number })}
              </Badge>
            ) : null}
            <ToolButton
              label={t("viewer.next")}
              icon={ChevronRight}
              disabled={selectedIndex < 0 || selectedIndex >= pages.length - 1}
              onClick={() => setSelectedId(pages[selectedIndex + 1].id)}
            />

            <span className="mx-1 h-5 w-px bg-border/70" aria-hidden="true" />

            <ToolButton
              label={t("viewer.rotateLeft")}
              icon={RotateCcw}
              disabled={rotatePage.isPending}
              onClick={() => rotate(-90)}
            />
            <ToolButton
              label={t("viewer.rotateRight")}
              icon={RotateCw}
              disabled={rotatePage.isPending}
              onClick={() => rotate(90)}
            />
            <ToolButton
              label={t("viewer.reset")}
              icon={Undo2}
              disabled={rotatePage.isPending || currentPage.rotation === 0}
              onClick={() => rotate(-currentPage.rotation)}
            />

            <span className="mx-1 h-5 w-px bg-border/70" aria-hidden="true" />

            <ToolButton
              label={t("ocr.open")}
              icon={ScanText}
              onClick={() => setOcrOpen(true)}
            />

            <ToolButton
              label={t(selectMode ? "elements.cancelSelect" : "elements.select")}
              icon={ScanSearch}
              active={selectMode}
              onClick={() =>
                selectMode ? cancelRegionSelect() : beginRegionSelect()
              }
            />

            <ToolButton
              label={t(
                proposalsOn ? "elements.proposals.hide" : "elements.proposals.show",
              )}
              icon={Sparkles}
              active={proposalsOn}
              onClick={() => {
                cancelRegionSelect();
                resetAiRegions();
                setProposalsOn((value) => !value);
              }}
            />

            <ToolButton
              label={
                aiRegionData
                  ? t("elements.ai.requestAgain")
                  : t("elements.ai.request")
              }
              icon={WandSparkles}
              active={Boolean(aiRegionData)}
              disabled={aiRegions.isPending || !currentPage}
              onClick={requestAiRegions}
            />

            <ToolButton
              label={
                elementCount > 0
                  ? t("elements.openCount", { count: elementCount })
                  : t("elements.open")
              }
              icon={Images}
              onClick={() => {
                cancelRegionSelect();
                setElementsOpen(true);
              }}
            />

            <ToolButton
              label={t(overlayOn ? "viewer.overlay.hide" : "viewer.overlay.show")}
              icon={Layers}
              active={overlayOn}
              onClick={() => setOverlayOn((value) => !value)}
            />

            <ToolButton
              label={t("edits.open")}
              icon={SlidersHorizontal}
              onClick={() => setEditsOpen(true)}
              disabled={!currentPage}
            />

            <div className="ml-auto flex items-center gap-0.5">
              <ToolButton
                label={t("viewer.zoomOut")}
                icon={ZoomOut}
                disabled={scale.kind === "zoom" && scale.value <= MIN_ZOOM}
                onClick={() => zoomBy(1 / 1.25)}
              />
              <span className="w-10 text-center font-mono text-2xs text-muted-foreground">
                {zoomPercent === null ? t("viewer.fit") : `${zoomPercent}%`}
              </span>
              <ToolButton
                label={t("viewer.zoomIn")}
                icon={ZoomIn}
                disabled={scale.kind === "zoom" && scale.value >= MAX_ZOOM}
                onClick={() => zoomBy(1.25)}
              />
              <ToolButton
                label={t("viewer.fit")}
                icon={Maximize2}
                active={scale.kind === "fit"}
                onClick={() => setScale({ kind: "fit" })}
              />
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant={scale.kind === "actual" ? "secondary" : "ghost"}
                    size="icon-xs"
                    aria-pressed={scale.kind === "actual"}
                    aria-label={t("viewer.actual")}
                    onClick={() => setScale({ kind: "actual" })}
                    className="font-mono text-[0.625rem]"
                  >
                    1:1
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{t("viewer.actual")}</TooltipContent>
              </Tooltip>
            </div>
          </div>

          {overlayOn ? (
            <div
              aria-live="polite"
              className="scrollbar-thin flex shrink-0 items-center gap-1.5 overflow-x-auto border-b border-border/60 bg-background/25 px-2 py-1 text-2xs text-muted-foreground"
            >
              <span className="shrink-0 font-semibold uppercase tracking-wider">
                {t("viewer.overlay.legend")}
              </span>
              {overlayMessage ? (
                <span className="whitespace-nowrap">{t(overlayMessage)}</span>
              ) : (
                overlayLegend.map(({ kind, count }) => (
                  <span
                    key={kind}
                    className="inline-flex shrink-0 items-center gap-1 rounded-pill border border-border/60 bg-background/70 px-1.5 py-0.5"
                  >
                    <span
                      aria-hidden="true"
                      className={cn("size-2 rounded-pill", LAYOUT_SWATCH_CLASS[kind])}
                    />
                    <span className="whitespace-nowrap">{t(`ocr.kind.${kind}`)}</span>
                    <span className="font-mono opacity-70">{count}</span>
                  </span>
                ))
              )}
              <span className="shrink-0 whitespace-nowrap border-l border-border/60 pl-2 opacity-80">
                {t("viewer.overlay.note")}
              </span>
            </div>
          ) : null}

          {proposalsOn ? (
            <div
              aria-live="polite"
              className="scrollbar-thin flex shrink-0 items-center gap-1.5 overflow-x-auto border-b border-border/60 bg-background/25 px-2 py-1 text-2xs text-muted-foreground"
            >
              <span className="shrink-0 font-semibold uppercase tracking-wider">
                {t("elements.proposals.title", {
                  count: proposalsQuery.data?.proposals.length ?? 0,
                })}
              </span>
              {proposalMessage ? (
                <span className="whitespace-nowrap">{t(proposalMessage)}</span>
              ) : null}
              <span className="shrink-0 whitespace-nowrap border-l border-border/60 pl-2 opacity-80">
                {t("elements.proposals.note")}
              </span>
            </div>
          ) : null}

          {aiRegions.isPending ? (
            <div
              aria-live="polite"
              className="flex shrink-0 items-center gap-2 border-b border-primary/30 bg-primary/5 px-2 py-1 text-2xs text-primary"
            >
              <Spinner className="size-3.5" />
              <span>{t("elements.ai.loading")}</span>
              <span className="truncate opacity-80">{t("elements.ai.loadingNote")}</span>
            </div>
          ) : aiRegionData ? (
            <div
              aria-live="polite"
              className="scrollbar-thin flex shrink-0 items-center gap-1.5 overflow-x-auto border-b border-border/60 bg-warning/5 px-2 py-1 text-2xs text-muted-foreground"
            >
              <span className="shrink-0 font-semibold uppercase tracking-wider text-warning">
                {t("elements.ai.title", { count: aiRegionData.proposals.length })}
              </span>
              <span className="whitespace-nowrap">
                {t("elements.ai.meta", {
                  provider: aiRegionData.provider,
                  model: aiRegionData.model,
                })}
              </span>
              <span className="shrink-0 whitespace-nowrap border-l border-border/60 pl-2">
                {t("elements.ai.lowConfidence")}
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="ml-auto shrink-0"
                onClick={() => resetAiRegions()}
              >
                {t("elements.ai.dismiss")}
              </Button>
            </div>
          ) : null}

          {selectMode ? (
            <div
              aria-live="polite"
              className="flex shrink-0 items-center gap-2 border-b border-primary/30 bg-primary/5 px-2 py-1 text-2xs text-primary"
            >
              <ScanSearch className="size-3.5 shrink-0" aria-hidden="true" />
              <span>{t("elements.selectHint")}</span>
              <Button
                variant="ghost"
                size="sm"
                className="ml-auto shrink-0"
                onClick={cancelRegionSelect}
              >
                {tCommon("actions.cancel")}
              </Button>
            </div>
          ) : null}

          <div className="flex min-h-0 flex-1 flex-col-reverse sm:flex-row">
            <PageThumbnails
              pages={pages}
              projectId={projectId}
              selectedId={currentPage.id}
              onSelect={setSelectedId}
              onMove={movePage}
              labelFor={labelFor}
              groupLabel={t("thumbnails")}
            />

            <div
              ref={viewportRef}
              className="scrollbar-thin relative flex min-w-0 flex-1 overflow-auto bg-muted/30"
            >
              <div
                ref={contentRef}
                onPointerDown={handleSelectStart}
                onPointerMove={handleSelectMove}
                onPointerUp={handleSelectEnd}
                onPointerCancel={abortDrag}
                className={cn(
                  "relative flex h-full min-h-full w-full p-4",
                  selectMode && "cursor-crosshair touch-none",
                )}
              >
                {imageSrc ? (
                  <>
                    <img
                      key={`${currentPage.id}-${currentPage.updated_at}`}
                      ref={imageRef}
                      src={imageSrc}
                      alt={currentPage.original_filename ?? labelFor(currentPage)}
                      draggable={false}
                      onLoad={measureImage}
                      style={imageStyle}
                      className={cn(
                        "m-auto block rounded-xs bg-card shadow-sm",
                        scale.kind === "fit"
                          ? "max-h-full max-w-full object-contain"
                          : "max-w-none",
                        (rotatePage.isPending || reorderPages.isPending) && "opacity-70",
                      )}
                    />
                    {overlayOn && imageFrame && overlayBoxes.length > 0 ? (
                      <div
                        aria-hidden="true"
                        className="pointer-events-none absolute animate-fade-in"
                        style={{
                          left: imageFrame.left,
                          top: imageFrame.top,
                          width: imageFrame.width,
                          height: imageFrame.height,
                        }}
                      >
                        {overlayBoxes.map((box) => (
                          <div
                            key={box.id}
                            className={cn(
                              "absolute rounded-xs border",
                              LAYOUT_BOX_CLASS[box.kind],
                            )}
                            style={{
                              left: box.left,
                              top: box.top,
                              width: box.width,
                              height: box.height,
                            }}
                          />
                        ))}
                      </div>
                    ) : null}
                    {imageFrame && proposalBoxes.length > 0 ? (
                      <div
                        className="absolute animate-fade-in"
                        style={{
                          left: imageFrame.left,
                          top: imageFrame.top,
                          width: imageFrame.width,
                          height: imageFrame.height,
                        }}
                      >
                        {proposalBoxes.map(({ proposal, box }) => (
                          <button
                            key={proposal.key}
                            type="button"
                            onClick={() => applyProposal(proposal)}
                            aria-label={t("elements.proposals.use", {
                              kind: t(`elements.kind.${proposal.kind}`),
                            })}
                            className={cn(
                              "focus-ring absolute rounded-xs border-2 border-dashed transition-colors",
                              proposal.reason === "ai_vision"
                                ? "border-warning/80 bg-warning/10 hover:bg-warning/20"
                                : "border-primary/70 bg-primary/10 hover:bg-primary/20",
                            )}
                            style={{
                              left: box.left,
                              top: box.top,
                              width: box.width,
                              height: box.height,
                            }}
                          >
                            <span
                              className={cn(
                                "pointer-events-none absolute left-1 top-1 rounded-pill bg-background/90 px-1.5 py-0.5 text-[0.625rem] font-medium leading-4 shadow-xs",
                                proposal.reason === "ai_vision"
                                  ? "text-warning"
                                  : "text-primary",
                              )}
                            >
                              {t(`elements.kind.${proposal.kind}`)}
                            </span>
                          </button>
                        ))}
                      </div>
                    ) : null}
                    {selectMode && dragStart && dragCurrent ? (
                      <div
                        aria-hidden="true"
                        className="pointer-events-none absolute border-2 border-primary bg-primary/15 shadow-sm"
                        style={displayRect(dragStart, dragCurrent)}
                      />
                    ) : null}
                  </>
                ) : (
                  <div className="m-auto flex flex-col items-center gap-2 text-xs text-muted-foreground">
                    <ImageIcon className="size-icon-lg" />
                    {t("viewer.emptyValue")}
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      ) : null}

      {dragging ? (
        <div className="pointer-events-none absolute inset-0 z-panel flex items-center justify-center bg-background/70 backdrop-blur-sm">
          <div className="flex flex-col items-center gap-2 rounded-xl border-2 border-dashed border-primary/60 bg-card/90 px-8 py-6 text-center shadow-lg">
            <Upload className="size-icon-lg text-primary" />
            <p className="text-sm font-semibold">
              {t(allowPdf ? "dropTitlePdf" : "dropTitle")}
            </p>
            <p className="text-xs text-muted-foreground">
              {meta
                ? t(allowPdf ? "supported" : "supportedNoPdf", {
                    size: meta.max_import_mb,
                  })
                : t("supportedNoSize")}
            </p>
          </div>
        </div>
      ) : null}

      <OcrDialog
        projectId={projectId}
        page={currentPage}
        open={ocrOpen}
        onOpenChange={setOcrOpen}
        onInserted={onContentInserted}
      />

      <ElementsDialog
        projectId={projectId}
        page={currentPage}
        open={elementsOpen}
        onOpenChange={handleElementsOpenChange}
        pendingSelection={pendingSelection}
        onPendingConsumed={consumePendingSelection}
        pendingProposal={pendingProposal}
        onProposalConsumed={consumePendingProposal}
        onRequestSelection={beginRegionSelect}
        onInserted={onContentInserted}
      />

      <EditsDialog
        projectId={projectId}
        page={currentPage}
        open={editsOpen}
        onOpenChange={setEditsOpen}
      />

      <Dialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("deletePageDialog.title")}</DialogTitle>
            <DialogDescription>{t("deletePageDialog.description")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              {tCommon("actions.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={deletePage.isPending}
              onClick={() => {
                if (!deleteTarget) return;
                const index = pages.findIndex((page) => page.id === deleteTarget.id);
                const next = pages[index + 1] ?? pages[index - 1] ?? null;
                deletePage.mutate(deleteTarget.id, {
                  onSuccess: () => {
                    setSelectedId(next?.id ?? null);
                    setDeleteTarget(null);
                  },
                  onError: (error) => toast.error(errorMessage(error)),
                });
              }}
            >
              {deletePage.isPending
                ? tCommon("loading")
                : t("deletePageDialog.confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
