import {
  ArrowLeft,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  Image as ImageIcon,
  Maximize2,
  MoreHorizontal,
  RotateCcw,
  RotateCw,
  ScanText,
  Trash2,
  Undo2,
  Upload,
  ZoomIn,
  ZoomOut,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type { PageSummary } from "@docurebuild/shared-types";

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
import { useAppMeta } from "@/hooks/use-app";
import {
  useDeletePage,
  useImportPages,
  usePages,
  useReorderPages,
  useRotatePage,
} from "@/hooks/use-projects";
import { api } from "@/lib/api";
import {
  IMAGE_ACCEPT_ATTRIBUTE,
  IMPORT_ACCEPT_ATTRIBUTE,
  partitionImportFiles,
} from "@/lib/import-files";
import { cn } from "@/lib/utils";
import { OcrDialog } from "./ocr-dialog";

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
  const pagesQuery = usePages(projectId);
  const metaQuery = useAppMeta();
  const pages = useMemo(() => pagesQuery.data ?? [], [pagesQuery.data]);
  const meta = metaQuery.data;

  const importPages = useImportPages(projectId);
  const rotatePage = useRotatePage(projectId);
  const deletePage = useDeletePage(projectId);
  const reorderPages = useReorderPages(projectId);
  const errorMessage = useApiErrorMessage();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [scale, setScale] = useState<ViewScale>({ kind: "fit" });
  const [dragging, setDragging] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<PageSummary | null>(null);
  const [ocrOpen, setOcrOpen] = useState(false);
  const dragDepth = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const selectedIndex = pages.findIndex((page) => page.id === selectedId);
  const currentPage = selectedIndex >= 0 ? pages[selectedIndex] : (pages[0] ?? null);

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

  const maxBytes = useMemo(
    () => (meta ? meta.max_import_mb * 1024 * 1024 : null),
    [meta],
  );
  const allowPdf = meta?.capabilities.import_pdf ?? false;

  const handleFiles = (files: FileList | File[]) => {
    const list = Array.from(files);
    if (list.length === 0 || importPages.isPending) return;

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

    importPages.mutate(accepted, {
      onSuccess: (imported) => {
        if (imported[0]) setSelectedId(imported[0].id);
        toast.success(t("importSuccess", { count: imported.length }));
      },
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
        {importPages.isPending ? (
          <span className="ml-1 flex items-center gap-1.5 text-2xs text-muted-foreground">
            <Spinner className="size-3.5" />
            <span className="hidden sm:inline">
              {t("importing", { count: importPages.variables?.length ?? 0 })}
            </span>
          </span>
        ) : null}

        <div className="ml-auto flex items-center gap-0.5">
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5 px-2"
            disabled={importPages.isPending}
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
            disabled={importPages.isPending}
            className="focus-ring group flex w-full max-w-sm flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border/90 bg-background/40 px-6 py-12 text-center transition-colors hover:border-primary/50 hover:bg-primary/5 disabled:pointer-events-none disabled:opacity-60"
          >
            <span className="flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary transition-transform duration-fast group-hover:scale-105">
              {importPages.isPending ? <Spinner className="size-icon-lg" /> : <Upload className="size-icon-lg" />}
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

            <div className="scrollbar-thin relative flex min-w-0 flex-1 overflow-auto bg-muted/30">
              <div className="flex h-full min-h-full w-full p-4">
                {imageSrc ? (
                  <img
                    key={`${currentPage.id}-${currentPage.updated_at}`}
                    src={imageSrc}
                    alt={currentPage.original_filename ?? labelFor(currentPage)}
                    draggable={false}
                    style={imageStyle}
                    className={cn(
                      "m-auto block rounded-xs bg-card shadow-sm",
                      scale.kind === "fit"
                        ? "max-h-full max-w-full object-contain"
                        : "max-w-none",
                      (rotatePage.isPending || reorderPages.isPending) && "opacity-70",
                    )}
                  />
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
