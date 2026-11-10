import {
  Crop,
  Image as ImageIcon,
  RefreshCw,
  RotateCcw,
  SlidersHorizontal,
  type LucideIcon,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type {
  PageEdits,
  PageGeometryStep,
  PagePerspectiveCorners,
  PageSummary,
} from "@docurebuild/shared-types";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Slider } from "@/components/ui/slider";
import { Separator } from "@/components/ui/separator";
import { Toggle } from "@/components/ui/toggle";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useUpdatePageEdits, useResetPageEdits, useEstimatePageSkew } from "@/hooks/use-projects";
import { api } from "@/lib/api";

interface EditsDialogProps {
  projectId: string;
  page: PageSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const DEFAULT_FILTERS: PageEdits["filters"] = {
  grayscale: false,
  contrast: 1.0,
  brightness: 1.0,
  sharpness: 1.0,
  denoise: 0,
  shadow_removal: false,
  background_cleanup: false,
  threshold: false,
  threshold_level: 55,
};

/** Corner order expected by the backend: top-left, bottom-left, bottom-right, top-right. */
const DEFAULT_PERSPECTIVE_CORNERS: [number, number][] = [
  [0, 0],
  [0, 1],
  [1, 1],
  [1, 0],
];

const MIN_PERSPECTIVE_AREA = 0.02;

function perspectiveArea(corners: [number, number][]): number {
  let area = 0;
  for (let index = 0; index < 4; index += 1) {
    const [x1, y1] = corners[index];
    const [x2, y2] = corners[(index + 1) % 4];
    area += x1 * y2 - x2 * y1;
  }
  return Math.abs(area) / 2;
}

function cloneCorners(corners: PagePerspectiveCorners | undefined): [number, number][] {
  if (!corners) {
    return DEFAULT_PERSPECTIVE_CORNERS.map(([x, y]) => [x, y]);
  }
  return [0, 1, 2, 3].map((index) => {
    const point = corners[index];
    return [Number(point?.[0]) || 0, Number(point?.[1]) || 0] as [number, number];
  });
}

function normaliseEdits(edits: PageEdits | undefined): PageEdits {
  return {
    geometry: Array.isArray(edits?.geometry) ? edits.geometry : [],
    filters: { ...DEFAULT_FILTERS, ...(edits?.filters ?? {}) },
  };
}

function hasActiveEdits(edits: PageEdits): boolean {
  if (edits.geometry.length > 0) return true;
  const f = edits.filters;
  const d = DEFAULT_FILTERS;
  return (
    f.grayscale !== d.grayscale ||
    f.contrast !== d.contrast ||
    f.brightness !== d.brightness ||
    f.sharpness !== d.sharpness ||
    f.denoise !== d.denoise ||
    f.shadow_removal !== d.shadow_removal ||
    f.background_cleanup !== d.background_cleanup ||
    f.threshold !== d.threshold ||
    f.threshold_level !== d.threshold_level
  );
}

function geometryIcon(type: PageGeometryStep["type"]): LucideIcon {
  switch (type) {
    case "crop":
      return Crop;
    case "perspective":
      return RotateCcw;
    case "deskew":
      return SlidersHorizontal;
  }
}

function FilterControl({
  label,
  value,
  onChange,
  min = 0.5,
  max = 2.5,
  step = 0.1,
  format = (v: number) => `${Math.round(v * 100)}%`,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  format?: (v: number) => string;
}) {
  const { t } = useTranslation("workspace");
  return (
    <div className="space-y-1">
      <label className="text-2xs font-medium text-muted-foreground flex items-center justify-between">
        <span>{t(label)}</span>
        <span className="font-mono text-xs">{format(value)}</span>
      </label>
      <Slider
        value={[value]}
        onValueChange={([v]) => onChange(v)}
        min={min}
        max={max}
        step={step}
        className="h-1.5"
      />
    </div>
  );
}

function DenoiseControl({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const { t } = useTranslation("workspace");
  return (
    <div className="space-y-1">
      <label className="text-2xs font-medium text-muted-foreground flex items-center justify-between">
        <span>{t("edits.filters.denoise")}</span>
        <span className="font-mono text-xs">{value === 0 ? t("edits.filters.off") : `Level ${value}`}</span>
      </label>
      <Slider
        value={[value]}
        onValueChange={([v]) => onChange(Math.round(v))}
        min={0}
        max={3}
        step={1}
        className="h-1.5"
      />
    </div>
  );
}

function ThresholdLevelControl({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const { t } = useTranslation("workspace");
  return (
    <div className="space-y-1">
      <label className="text-2xs font-medium text-muted-foreground flex items-center justify-between">
        <span>{t("edits.filters.thresholdLevel")}</span>
        <span className="font-mono text-xs">{value}%</span>
      </label>
      <Slider
        value={[value]}
        onValueChange={([v]) => onChange(Math.round(v))}
        min={1}
        max={99}
        step={1}
        className="h-1.5"
      />
    </div>
  );
}

export function EditsDialog({ projectId, page, open, onOpenChange }: EditsDialogProps) {
  const { t } = useTranslation("workspace");
  const { t: tCommon } = useTranslation("common");
  const errorMessage = useApiErrorMessage();
  const updateEdits = useUpdatePageEdits(projectId);
  const resetEdits = useResetPageEdits(projectId);
  const estimateSkew = useEstimatePageSkew(projectId);

  const [edits, setEdits] = useState<PageEdits>({ geometry: [], filters: DEFAULT_FILTERS });
  const [activeTool, setActiveTool] = useState<PageGeometryStep["type"] | null>(null);
  const [comparingBase, setComparingBase] = useState(false);
  const [preview, setPreview] = useState<{ src: string; version: number } | null>(null);
  const [perspectiveCorners, setPerspectiveCorners] = useState<[number, number][]>(() =>
    cloneCorners(undefined),
  );
  const [draggingCorner, setDraggingCorner] = useState<number | null>(null);
  const [imageBox, setImageBox] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const dragRef = useRef<{ startX: number; startY: number; rect: PageEdits["geometry"][0]["rect"] } | null>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const previewCounter = useRef(0);
  const initializedPageRef = useRef<string | null>(null);
  const editsRef = useRef(edits);
  editsRef.current = edits;
  const perspectiveCornersRef = useRef(perspectiveCorners);
  perspectiveCornersRef.current = perspectiveCorners;

  const currentEdits = useMemo(() => normaliseEdits(page?.edits), [page?.edits]);
  const hasEdits = hasActiveEdits(currentEdits);

  const refreshPreview = useCallback(
    (useBase = comparingBase, target: PageSummary | null = page) => {
      if (!target) return;
      previewCounter.current += 1;
      const version = previewCounter.current;
      const url = useBase
        ? api.pageBasePreview(projectId, target.id)
        : api.assetUrl(projectId, target.display_asset_id ?? target.original_asset_id, target.updated_at);
      if (!url) {
        setPreview(null);
        return;
      }
      const separator = url.includes("?") ? "&" : "?";
      setPreview({ src: `${url}${separator}r=${version}`, version });
    },
    [page, projectId, comparingBase],
  );

  const measureImage = useCallback(() => {
    const image = imageRef.current;
    const container = containerRef.current;
    if (!image || !container || image.naturalWidth === 0) {
      setImageBox(null);
      return;
    }
    const imageRect = image.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    setImageBox({
      left: imageRect.left - containerRect.left + container.scrollLeft,
      top: imageRect.top - containerRect.top + container.scrollTop,
      width: imageRect.width,
      height: imageRect.height,
    });
  }, []);

  useEffect(() => {
    if (!open || activeTool !== "perspective") {
      setImageBox(null);
      return;
    }
    measureImage();
    const observer = new ResizeObserver(() => measureImage());
    if (containerRef.current) observer.observe(containerRef.current);
    if (imageRef.current) observer.observe(imageRef.current);
    window.addEventListener("resize", measureImage);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measureImage);
    };
  }, [open, activeTool, preview?.version, measureImage]);

  useEffect(() => {
    if (!open) {
      initializedPageRef.current = null;
      return;
    }
    if (!page || initializedPageRef.current === page.id) return;
    initializedPageRef.current = page.id;
    const initial = normaliseEdits(page.edits);
    editsRef.current = initial;
    setEdits(initial);
    setActiveTool(null);
    setComparingBase(false);
    const existing = initial.geometry.find((step) => step.type === "perspective");
    setPerspectiveCorners(cloneCorners(existing?.corners));
    refreshPreview(false);
  }, [open, page, refreshPreview]);

  const applyEdits = async (newEdits: PageEdits) => {
    if (!page) return;
    editsRef.current = newEdits;
    setEdits(newEdits);
    try {
      const updated = await updateEdits.mutateAsync({ pageId: page.id, edits: newEdits });
      toast.success(t("edits.applied"));
      setComparingBase(false);
      refreshPreview(false, updated);
    } catch (error) {
      toast.error(errorMessage(error));
      const reverted = normaliseEdits(page.edits);
      editsRef.current = reverted;
      setEdits(reverted);
    }
  };

  const handleReset = async () => {
    if (!page) return;
    try {
      const updated = await resetEdits.mutateAsync(page.id);
      const cleared: PageEdits = { geometry: [], filters: DEFAULT_FILTERS };
      editsRef.current = cleared;
      setEdits(cleared);
      setActiveTool(null);
      setComparingBase(false);
      initializedPageRef.current = null;
      refreshPreview(false, updated);
      toast.success(t("edits.reset"));
    } catch (error) {
      toast.error(errorMessage(error));
    }
  };

  const toggleCompare = () => {
    const next = !comparingBase;
    setComparingBase(next);
    refreshPreview(next);
  };

  const handleAutoDeskew = async () => {
    if (!page) return;
    try {
      const { angle } = await estimateSkew.mutateAsync(page.id);
      if (Math.abs(angle) < 0.1) {
        toast.info(t("edits.deskew.alreadyStraight"));
        return;
      }
      const current = editsRef.current;
      const geometry = current.geometry.filter((g) => g.type !== "deskew");
      geometry.push({ type: "deskew", angle: Math.round(angle * 10) / 10 });
      await applyEdits({ ...current, geometry });
      toast.success(t("edits.deskew.applied", { angle: angle.toFixed(1) }));
    } catch (error) {
      toast.error(errorMessage(error));
    }
  };

  const updateFilter = <K extends keyof PageEdits["filters"]>(key: K, value: PageEdits["filters"][K]) => {
    const current = editsRef.current;
    applyEdits({ ...current, filters: { ...current.filters, [key]: value } });
  };

  const addGeometry = (step: PageGeometryStep) => {
    const current = editsRef.current;
    const replaceable = step.type === "crop" || step.type === "perspective" ? step.type : null;
    const base = replaceable
      ? current.geometry.filter((g) => g.type !== replaceable)
      : current.geometry;
    const geometry = [...base, step];
    if (geometry.length > 8) {
      toast.error(t("edits.tooManySteps"));
      return;
    }
    void applyEdits({ ...current, geometry });
  };

  const removeGeometry = (index: number) => {
    const geometry = edits.geometry.filter((_, i) => i !== index);
    applyEdits({ ...edits, geometry });
  };

  const startCrop = () => {
    if (activeTool === "crop") {
      setActiveTool(null);
      return;
    }
    setActiveTool("crop");
    toast.info(t("edits.crop.hint"));
  };

  const startPerspective = () => {
    if (activeTool === "perspective") {
      setActiveTool(null);
      return;
    }
    const current = editsRef.current;
    const existing = current.geometry.find((step) => step.type === "perspective");
    setPerspectiveCorners(cloneCorners(existing?.corners));
    setActiveTool("perspective");
    toast.info(t("edits.perspective.hint"));
  };

  const handleCornerPointerDown = (index: number) => (event: ReactPointerEvent<HTMLDivElement>) => {
    if (comparingBase) return;
    event.preventDefault();
    event.stopPropagation();
    setDraggingCorner(index);

    const move = (e: PointerEvent) => {
      const image = imageRef.current;
      if (!image) return;
      const rect = image.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      const x = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
      const y = Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height));
      setPerspectiveCorners((prev) => {
        const next = prev.map(([px, py]) => [px, py] as [number, number]);
        next[index] = [Math.round(x * 1000) / 1000, Math.round(y * 1000) / 1000];
        return next;
      });
    };

    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      setDraggingCorner(null);
      const corners = perspectiveCornersRef.current;
      if (perspectiveArea(corners) < MIN_PERSPECTIVE_AREA) {
        toast.error(t("edits.perspective.tooSmall"));
        return;
      }
      addGeometry({ type: "perspective", corners: corners as PagePerspectiveCorners });
      setActiveTool(null);
    };

    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const handleCornerKeyDown = (index: number, event: ReactKeyboardEvent<HTMLDivElement>) => {
    const commit = () => {
      const corners = perspectiveCornersRef.current;
      if (perspectiveArea(corners) < MIN_PERSPECTIVE_AREA) {
        toast.error(t("edits.perspective.tooSmall"));
        return;
      }
      addGeometry({ type: "perspective", corners: corners as PagePerspectiveCorners });
      setActiveTool(null);
    };

    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      commit();
      return;
    }

    const step = event.shiftKey ? 0.05 : 0.01;
    const delta: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    };
    const shift = delta[event.key];
    if (!shift) return;
    event.preventDefault();
    setPerspectiveCorners((prev) => {
      const next = prev.map(([px, py]) => [px, py] as [number, number]);
      const [x, y] = next[index];
      const round = (value: number) => Math.round(Math.min(1, Math.max(0, value)) * 1000) / 1000;
      next[index] = [round(x + shift[0]), round(y + shift[1])];
      return next;
    });
  };

  const handleImagePointerDown = (event: ReactPointerEvent<HTMLImageElement>) => {
    if (activeTool !== "crop" || !imageRef.current || !containerRef.current) return;
    event.preventDefault();
    const rect = imageRef.current.getBoundingClientRect();
    const scaleX = imageRef.current.naturalWidth / rect.width;
    const scaleY = imageRef.current.naturalHeight / rect.height;
    const startX = (event.clientX - rect.left) * scaleX;
    const startY = (event.clientY - rect.top) * scaleY;

    dragRef.current = {
      startX,
      startY,
      rect: { x: 0, y: 0, width: 1, height: 1 },
    };

    const move = (e: PointerEvent) => {
      if (!dragRef.current || !imageRef.current) return;
      const r = imageRef.current.getBoundingClientRect();
      const sX = imageRef.current.naturalWidth / r.width;
      const sY = imageRef.current.naturalHeight / r.height;
      const currentX = Math.max(0, Math.min(imageRef.current.naturalWidth, (e.clientX - r.left) * sX));
      const currentY = Math.max(0, Math.min(imageRef.current.naturalHeight, (e.clientY - r.top) * sY));
      const x = Math.min(dragRef.current.startX, currentX) / imageRef.current.naturalWidth;
      const y = Math.min(dragRef.current.startY, currentY) / imageRef.current.naturalHeight;
      const width = Math.abs(currentX - dragRef.current.startX) / imageRef.current.naturalWidth;
      const height = Math.abs(currentY - dragRef.current.startY) / imageRef.current.naturalHeight;
      if (width > 0.02 && height > 0.02) {
        const rect = { x, y, width, height };
        dragRef.current.rect = rect;
        setEdits((prev) => {
          const geom = prev.geometry.filter((g) => g.type !== "crop");
          geom.push({ type: "crop", rect });
          return { ...prev, geometry: geom };
        });
      }
    };

    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      const rect = dragRef.current?.rect;
      if (rect) {
        addGeometry({ type: "crop", rect });
      }
      setActiveTool(null);
      dragRef.current = null;
    };

    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const filterValue = (key: keyof PageEdits["filters"]) => edits.filters[key] as number;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] max-w-4xl flex-col gap-4 overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ImageIcon className="size-icon-sm text-primary" aria-hidden="true" />
            {t("edits.title", { page: page?.page_number ?? "\u2014" })}
          </DialogTitle>
          <DialogDescription>{t("edits.description")}</DialogDescription>
        </DialogHeader>

        <div className="flex min-h-0 flex-1 overflow-hidden">
          <div
            className="scrollbar-thin relative w-full min-w-0 flex-1 bg-muted/30"
            ref={containerRef}
            onScroll={activeTool === "perspective" ? measureImage : undefined}
          >
            <div className="flex h-full min-h-full w-full p-4">
              {page && preview ? (
                <img
                  ref={imageRef}
                  key={`preview-${page.id}-${preview.version}`}
                  src={preview.src}
                  alt={page.original_filename ?? t("viewer.pageOf", { page: page.page_number, total: 1 })}
                  draggable={false}
                  className="m-auto block max-h-full max-w-full object-contain rounded-xs bg-card shadow-sm"
                  style={{
                    filter: comparingBase
                      ? undefined
                      : edits.filters.grayscale
                        ? "grayscale(1)"
                        : edits.filters.threshold
                          ? `contrast(${edits.filters.contrast}) brightness(${edits.filters.brightness})`
                          : undefined,
                    cursor: !comparingBase
                      ? activeTool === "crop"
                        ? "crosshair"
                        : activeTool === "perspective"
                          ? "default"
                          : undefined
                      : undefined,
                  }}
                  onLoad={measureImage}
                  onPointerDown={comparingBase ? undefined : handleImagePointerDown}
                />
              ) : (
                <div className="m-auto flex flex-col items-center gap-2 text-xs text-muted-foreground">
                  <ImageIcon className="size-icon-lg" />
                  {t("viewer.emptyValue")}
                </div>
              )}
            </div>

            {page && preview && activeTool === "perspective" && !comparingBase && imageBox ? (
              <div
                className="pointer-events-none absolute z-10"
                style={{
                  left: imageBox.left,
                  top: imageBox.top,
                  width: imageBox.width,
                  height: imageBox.height,
                }}
              >
                <svg
                  viewBox="0 0 1 1"
                  preserveAspectRatio="none"
                  className="absolute inset-0 h-full w-full"
                  aria-hidden="true"
                >
                  <polygon
                    points={perspectiveCorners.map(([x, y]) => `${x},${y}`).join(" ")}
                    className="fill-primary/10 stroke-primary"
                    strokeWidth={2}
                    vectorEffect="non-scaling-stroke"
                  />
                </svg>
                {perspectiveCorners.map(([x, y], index) => (
                  <div
                    key={`corner-${index}`}
                    role="button"
                    tabIndex={0}
                    aria-label={t("edits.perspective.corner", { index: index + 1 })}
                    onPointerDown={handleCornerPointerDown(index)}
                    onKeyDown={(event) => handleCornerKeyDown(index, event)}
                    className={`pointer-events-auto absolute size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-primary bg-background shadow-sm transition-transform focus-ring ${
                      draggingCorner === index ? "scale-125 cursor-grabbing" : "cursor-grab"
                    }`}
                    style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
                  />
                ))}
              </div>
            ) : null}
          </div>

          <div className="w-72 shrink-0 border-l border-border/60 bg-background/35 p-3 overflow-y-auto">
            <div className="space-y-4">
              <div className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t("edits.geometry.title")}
                </h3>
                <div className="grid grid-cols-2 gap-1.5">
                  <Toggle
                    type="button"
                    pressed={activeTool === "crop"}
                    onPressedChange={() => startCrop()}
                    className="focus-ring flex h-control-sm min-w-0 items-center justify-center gap-1.5 rounded-md px-2 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground data-[state=on]:bg-primary data-[state=on]:text-primary-foreground"
                  >
                    <Crop className="size-icon-xs" aria-hidden="true" />
                    <span className="truncate">{t("edits.geometry.crop")}</span>
                  </Toggle>
                  <Toggle
                    type="button"
                    pressed={activeTool === "perspective"}
                    onPressedChange={() => startPerspective()}
                    className="focus-ring flex h-control-sm min-w-0 items-center justify-center gap-1.5 rounded-md px-2 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground data-[state=on]:bg-primary data-[state=on]:text-primary-foreground"
                  >
                    <RotateCcw className="size-icon-xs" aria-hidden="true" />
                    <span className="truncate">{t("edits.geometry.perspective")}</span>
                  </Toggle>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleAutoDeskew}
                    disabled={estimateSkew.isPending}
                    className="col-span-2 min-w-0"
                  >
                    <SlidersHorizontal className="size-icon-xs" aria-hidden="true" />
                    <span className="truncate">{t("edits.geometry.deskew")}</span>
                  </Button>
                </div>

                {edits.geometry.length > 0 && (
                  <div className="space-y-1.5">
                    <Separator />
                    <h4 className="text-2xs font-medium text-muted-foreground">{t("edits.geometry.applied")}</h4>
                    {edits.geometry.map((step, index) => {
                      const StepIcon = geometryIcon(step.type);
                      return (
                        <div
                          key={`${step.type}-${index}`}
                          className="flex items-center justify-between gap-2 rounded border border-border/70 bg-background/50 px-2 py-1.5"
                        >
                          <span className="flex items-center gap-1.5 text-2xs">
                            <StepIcon className="size-icon-xs text-muted-foreground" aria-hidden="true" />
                            <span>
                              {step.type === "crop" && step.rect
                                ? t("edits.geometry.cropRect", {
                                    x: Math.round(step.rect.x * 100),
                                    y: Math.round(step.rect.y * 100),
                                    w: Math.round(step.rect.width * 100),
                                    h: Math.round(step.rect.height * 100),
                                  })
                                : step.type === "deskew" && step.angle
                                ? t("edits.geometry.deskewAngle", { angle: step.angle.toFixed(1) })
                                : t(`edits.geometry.${step.type}`)}
                            </span>
                          </span>
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            onClick={() => removeGeometry(index)}
                            aria-label={t("edits.geometry.remove", { index: index + 1 })}
                          >
                            <RefreshCw className="size-icon-xs" />
                          </Button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t("edits.filters.title")}
                </h3>
                <div className="space-y-3">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="size-4 accent-primary"
                      checked={edits.filters.grayscale}
                      onChange={(e) => updateFilter("grayscale", e.target.checked)}
                    />
                    <span>{t("edits.filters.grayscale")}</span>
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="size-4 accent-primary"
                      checked={edits.filters.shadow_removal}
                      onChange={(e) => updateFilter("shadow_removal", e.target.checked)}
                    />
                    <span>{t("edits.filters.shadowRemoval")}</span>
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="size-4 accent-primary"
                      checked={edits.filters.background_cleanup}
                      onChange={(e) => updateFilter("background_cleanup", e.target.checked)}
                    />
                    <span>{t("edits.filters.backgroundCleanup")}</span>
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="size-4 accent-primary"
                      checked={edits.filters.threshold}
                      onChange={(e) => updateFilter("threshold", e.target.checked)}
                    />
                    <span>{t("edits.filters.threshold")}</span>
                  </label>
                  {edits.filters.threshold && (
                    <ThresholdLevelControl value={filterValue("threshold_level")} onChange={(v) => updateFilter("threshold_level", v)} />
                  )}
                  <FilterControl
                    label="edits.filters.contrast"
                    value={filterValue("contrast")}
                    onChange={(v) => updateFilter("contrast", v)}
                    min={0.5}
                    max={2.5}
                  />
                  <FilterControl
                    label="edits.filters.brightness"
                    value={filterValue("brightness")}
                    onChange={(v) => updateFilter("brightness", v)}
                    min={0.5}
                    max={1.5}
                  />
                  <FilterControl
                    label="edits.filters.sharpness"
                    value={filterValue("sharpness")}
                    onChange={(v) => updateFilter("sharpness", v)}
                    min={0.5}
                    max={2.5}
                  />
                  <DenoiseControl value={filterValue("denoise")} onChange={(v) => updateFilter("denoise", v)} />
                </div>
              </div>
            </div>
          </div>
        </div>

        <DialogFooter className="mt-0 shrink-0 items-stretch gap-2 border-t border-border/60 pt-3">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tCommon("actions.close")}
          </Button>
          {hasEdits && (
            <>
              <Button variant="outline" onClick={handleReset} disabled={resetEdits.isPending}>
                <RefreshCw className="size-icon-xs" />
                {t("edits.reset")}
              </Button>
              <Button
                variant="outline"
                aria-pressed={comparingBase}
                className={comparingBase ? "border-primary/60 text-primary" : undefined}
                onClick={toggleCompare}
                disabled={updateEdits.isPending}
              >
                {comparingBase ? t("edits.compareEdited") : t("edits.compareBase")}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}