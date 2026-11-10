import {
  Check,
  CheckCheck,
  CircleAlert,
  Crop,
  ImagePlus,
  Languages,
  Pencil,
  Pilcrow,
  ScanSearch,
  ScanText,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type { ElementKind, PageSummary, RegionProposal } from "@docurebuild/shared-types";

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
import { Input, Textarea } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import {
  useCreateElement,
  useDeleteElement,
  useElements,
  useExtractElementText,
  useUpdateElement,
  useUpdateElementText,
} from "@/hooks/use-elements";
import { useOcrCapabilities } from "@/hooks/use-ocr";
import { api } from "@/lib/api";
import { MIN_REGION_SIDE, type SourceRect } from "@/lib/element-region";
import { buildLanguageOptions, confidenceVariant, languageLabel } from "@/lib/ocr-display";
import { cn } from "@/lib/utils";
import { useWorkspaceActions } from "./workspace-actions-context";

interface ElementsDialogProps {
  projectId: string;
  page: PageSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** A marquee selection made on the source page, in source pixels. */
  pendingSelection: SourceRect | null;
  onPendingConsumed: () => void;
  /** A reviewed suggestion chosen on the source page overlay. */
  pendingProposal: RegionProposal | null;
  onProposalConsumed: () => void;
  onRequestSelection: () => void;
  onInserted?: () => void;
}

const KINDS: readonly ElementKind[] = ["figure", "table", "equation"];

interface CoordinateDraft {
  x: string;
  y: string;
  width: string;
  height: string;
}

const EMPTY_DRAFT: CoordinateDraft = { x: "", y: "", width: "", height: "" };

function draftFromRect(rect: SourceRect): CoordinateDraft {
  return {
    x: String(rect.x),
    y: String(rect.y),
    width: String(rect.width),
    height: String(rect.height),
  };
}

function parseRect(draft: CoordinateDraft): SourceRect | null {
  const values = [draft.x, draft.y, draft.width, draft.height];
  if (values.some((value) => value.trim() === "")) return null;
  const [x, y, width, height] = values.map(Number);
  if (![x, y, width, height].every(Number.isFinite)) return null;
  if (![x, y, width, height].every(Number.isInteger)) return null;
  if (x < 0 || y < 0) return null;
  if (width < MIN_REGION_SIDE || height < MIN_REGION_SIDE) return null;
  return { x, y, width, height };
}

function RegionPreview({
  src,
  pageWidth,
  pageHeight,
  rect,
}: {
  src: string | null;
  pageWidth: number | null;
  pageHeight: number | null;
  rect: SourceRect | null;
}) {
  if (!src || !rect || !pageWidth || !pageHeight) return null;
  if (rect.x + rect.width > pageWidth || rect.y + rect.height > pageHeight) return null;

  return (
    <div
      className="relative shrink-0 overflow-hidden rounded-md border border-border/70 bg-muted/30"
      style={{
        width: "7rem",
        aspectRatio: `${rect.width} / ${rect.height}`,
        maxHeight: "7rem",
      }}
      aria-hidden="true"
    >
      <img
        src={src}
        alt=""
        draggable={false}
        className="absolute max-w-none select-none"
        style={{
          width: `${(pageWidth / rect.width) * 100}%`,
          left: `${(-rect.x / rect.width) * 100}%`,
          top: `${(-rect.y / rect.height) * 100}%`,
        }}
      />
    </div>
  );
}

export function ElementsDialog({
  projectId,
  page,
  open,
  onOpenChange,
  pendingSelection,
  onPendingConsumed,
  pendingProposal,
  onProposalConsumed,
  onRequestSelection,
  onInserted,
}: ElementsDialogProps) {
  const { t } = useTranslation("workspace");
  const { t: tCommon } = useTranslation("common");
  const errorMessage = useApiErrorMessage();
  const { insertFigure, insertText } = useWorkspaceActions();

  const elementsQuery = useElements(projectId, page?.id ?? null, open);
  const elements = useMemo(
    () => elementsQuery.data ?? [],
    [elementsQuery.data],
  );
  const createElement = useCreateElement(projectId, page?.id ?? "");
  const updateElement = useUpdateElement(projectId, page?.id ?? "");
  const deleteElement = useDeleteElement(projectId, page?.id ?? "");
  const extractText = useExtractElementText(projectId, page?.id ?? "");
  const updateText = useUpdateElementText(projectId, page?.id ?? "");
  const capabilitiesQuery = useOcrCapabilities();
  const capabilities = capabilitiesQuery.data;

  const [kind, setKind] = useState<ElementKind>("figure");
  const [caption, setCaption] = useState("");
  const [draft, setDraft] = useState<CoordinateDraft>(EMPTY_DRAFT);
  const [includeNote, setIncludeNote] = useState(true);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [captionDraft, setCaptionDraft] = useState("");
  const [editingTextId, setEditingTextId] = useState<string | null>(null);
  const [textDraft, setTextDraft] = useState("");
  const [languageValue, setLanguageValue] = useState("eng");
  const [saving, setSaving] = useState(false);
  const [fromProposal, setFromProposal] = useState(false);

  const languageOptions = useMemo(
    () => buildLanguageOptions(capabilities?.languages, t),
    [capabilities, t],
  );

  useEffect(() => {
    if (!open || !capabilities) return;
    setLanguageValue((current) => {
      if (languageOptions.some((option) => option.value === current)) return current;
      if (languageOptions.some((option) => option.value === "eng")) return "eng";
      return languageOptions[0]?.value ?? "eng";
    });
  }, [open, capabilities, languageOptions]);

  const rect = parseRect(draft);
  const pageSrc = page
    ? api.assetUrl(projectId, page.display_asset_id ?? page.original_asset_id, page.updated_at)
    : null;

  useEffect(() => {
    if (!open) {
      setKind("figure");
      setCaption("");
      setDraft(EMPTY_DRAFT);
      setIncludeNote(true);
      setDeleteId(null);
      setEditingId(null);
      setCaptionDraft("");
      setEditingTextId(null);
      setTextDraft("");
      setFromProposal(false);
      return;
    }
    if (!pendingSelection) return;
    setDraft(draftFromRect(pendingSelection));
    onPendingConsumed();
  }, [open, pendingSelection, onPendingConsumed]);

  useEffect(() => {
    if (!open || !pendingProposal) return;
    setKind(pendingProposal.kind);
    setCaption(pendingProposal.caption);
    setDraft(draftFromRect(pendingProposal));
    setFromProposal(true);
    onProposalConsumed();
  }, [open, pendingProposal, onProposalConsumed]);

  const resetForm = () => {
    setCaption("");
    setDraft(EMPTY_DRAFT);
    setKind("figure");
    setFromProposal(false);
  };

  const save = async (insert: boolean) => {
    if (!page) return;
    if (!rect) {
      toast.error(t("elements.errors.invalidRegion"));
      return;
    }
    if (page.width && page.height) {
      if (rect.x + rect.width > page.width || rect.y + rect.height > page.height) {
        toast.error(t("elements.errors.outsidePage"));
        return;
      }
    }

    setSaving(true);
    try {
      const element = await createElement.mutateAsync({
        kind,
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
        caption,
      });
      if (insert) {
        const url = api.assetUrl(projectId, element.asset_id, element.updated_at);
        if (url) {
          insertFigure({
            src: url,
            alt: element.caption || t(`elements.kind.${element.kind}`),
            caption: element.caption,
            note: includeNote
              ? t("elements.sourceNote", {
                  page: page.page_number,
                  status: element.verified ? t("elements.verified") : t("elements.unverified"),
                })
              : null,
            width: element.width,
            height: element.height,
          });
          toast.success(t("elements.inserted"));
          onInserted?.();
        }
      } else {
        toast.success(t("elements.saved"));
      }
      resetForm();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  const insertSaved = (elementId: string) => {
    const element = elements.find((item) => item.id === elementId);
    if (!element || !page) return;
    const url = api.assetUrl(projectId, element.asset_id, element.updated_at);
    if (!url) {
      toast.error(t("elements.errors.missingAsset"));
      return;
    }
    insertFigure({
      src: url,
      alt: element.caption || t(`elements.kind.${element.kind}`),
      caption: element.caption,
      note: includeNote
        ? t("elements.sourceNote", {
            page: page.page_number,
            status: element.verified ? t("elements.verified") : t("elements.unverified"),
          })
        : null,
      width: element.width,
      height: element.height,
    });
    toast.success(t("elements.inserted"));
    onInserted?.();
  };

  const remove = (elementId: string) => {
    deleteElement.mutate(elementId, {
      onSuccess: () => {
        setDeleteId(null);
        if (editingId === elementId) setEditingId(null);
        toast.success(t("elements.deleted"));
      },
      onError: (error) => toast.error(errorMessage(error)),
    });
  };

  const startCaptionEdit = (elementId: string, caption: string) => {
    setEditingId(elementId);
    setCaptionDraft(caption);
  };

  const saveCaption = (elementId: string) => {
    const current = elements.find((item) => item.id === elementId)?.caption ?? "";
    const caption = captionDraft.trim();
    if (caption === current) {
      setEditingId(null);
      return;
    }
    updateElement.mutate(
      { elementId, caption },
      {
        onSuccess: () => {
          setEditingId(null);
          toast.success(t("elements.captionUpdated"));
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  };

  const toggleVerified = (elementId: string, verified: boolean) => {
    updateElement.mutate(
      { elementId, verified },
      { onError: (error) => toast.error(errorMessage(error)) },
    );
  };

  const extractElementText = (elementId: string) => {
    const languages = languageValue.split("+").filter(Boolean);
    extractText.mutate(
      { elementId, languages },
      {
        onSuccess: (element) => {
          setEditingTextId(null);
          setTextDraft("");
          toast.success(
            element.text
              ? t("elements.text.extracted")
              : t("elements.text.noTextDetected"),
          );
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  };

  const startTextEdit = (elementId: string, text: string) => {
    setEditingTextId(elementId);
    setTextDraft(text);
  };

  const saveText = (elementId: string) => {
    updateText.mutate(
      { elementId, text: textDraft },
      {
        onSuccess: () => {
          setEditingTextId(null);
          toast.success(t("elements.text.updated"));
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  };

  const insertElementText = (elementId: string) => {
    const element = elements.find((item) => item.id === elementId);
    if (!element || !page || !element.text.trim()) return;
    const status = element.verified
      ? t("elements.verified")
      : t("elements.unverified");
    let note: string | null = null;
    if (includeNote) {
      if (!element.text_engine) {
        note = t("elements.text.sourceNoteManual", {
          page: page.page_number,
          status,
        });
      } else if (element.text_corrected) {
        note = t("elements.text.sourceNoteCorrected", {
          page: page.page_number,
          engine: element.text_engine,
          status,
        });
      } else {
        note = t("elements.text.sourceNote", {
          page: page.page_number,
          confidence:
            element.text_confidence === null
              ? "—"
              : Math.round(element.text_confidence),
          status,
        });
      }
    }
    insertText(element.text, note);
    toast.success(t("elements.text.inserted"));
    onInserted?.();
  };

  const extractingId = extractText.isPending
    ? (extractText.variables?.elementId ?? null)
    : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] max-w-3xl flex-col gap-4 overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ScanSearch className="size-icon-sm text-primary" aria-hidden="true" />
            {t("elements.title", { page: page?.page_number ?? "—" })}
          </DialogTitle>
          <DialogDescription>{t("elements.description")}</DialogDescription>
        </DialogHeader>

        <div className="scrollbar-thin -mx-1 min-h-0 flex-1 space-y-4 overflow-y-auto px-1">
          <section className="rounded-lg border border-border/70 bg-background/45 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                {t("elements.newRegion")}
              </h3>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={onRequestSelection}
                disabled={!page}
              >
                <Crop />
                {t("elements.selectOnPage")}
              </Button>
            </div>

            {fromProposal ? (
              <p className="mt-2 flex items-start gap-1.5 rounded-md border border-primary/25 bg-primary/5 px-2 py-1.5 text-2xs leading-relaxed text-primary">
                <Sparkles className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
                {t("elements.proposals.prefilled")}
              </p>
            ) : null}

            <div className="mt-3 flex flex-col gap-3 sm:flex-row">
              <RegionPreview
                src={pageSrc}
                pageWidth={page?.width ?? null}
                pageHeight={page?.height ?? null}
                rect={rect}
              />
              <div className="min-w-0 flex-1 space-y-2.5">
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="space-y-1">
                    <label className="text-2xs font-medium text-muted-foreground">
                      {t("elements.kindLabel")}
                    </label>
                    <Select value={kind} onValueChange={(value) => setKind(value as ElementKind)}>
                      <SelectTrigger className="h-control" aria-label={t("elements.kindLabel")}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {KINDS.map((value) => (
                          <SelectItem key={value} value={value}>
                            {t(`elements.kind.${value}`)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <label
                      htmlFor="element-caption"
                      className="text-2xs font-medium text-muted-foreground"
                    >
                      {t("elements.caption")}
                    </label>
                    <Input
                      id="element-caption"
                      value={caption}
                      maxLength={500}
                      placeholder={t("elements.captionPlaceholder")}
                      onChange={(event) => setCaption(event.target.value)}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {(
                    [
                      ["x", t("elements.x")],
                      ["y", t("elements.y")],
                      ["width", t("elements.width")],
                      ["height", t("elements.height")],
                    ] as const
                  ).map(([key, label]) => (
                    <div key={key} className="space-y-1">
                      <label
                        htmlFor={`element-${key}`}
                        className="text-2xs font-medium text-muted-foreground"
                      >
                        {label}
                      </label>
                      <Input
                        id={`element-${key}`}
                        type="number"
                        min={0}
                        value={draft[key]}
                        inputMode="numeric"
                        onChange={(event) =>
                          setDraft((current) => ({ ...current, [key]: event.target.value }))
                        }
                      />
                    </div>
                  ))}
                </div>

                <p className="text-2xs leading-relaxed text-muted-foreground">
                  {t("elements.coordinateHint")}
                </p>
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <label className="flex items-center gap-1.5 text-2xs text-muted-foreground">
                <input
                  type="checkbox"
                  className="size-3.5 accent-primary"
                  checked={includeNote}
                  onChange={(event) => setIncludeNote(event.target.checked)}
                />
                {t("elements.includeNote")}
              </label>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void save(false)}
                  disabled={saving || !rect || !page}
                >
                  {t("elements.saveOnly")}
                </Button>
                <Button
                  size="sm"
                  className="gap-1.5"
                  onClick={() => void save(true)}
                  disabled={saving || !rect || !page}
                >
                  {saving ? <Spinner className="size-icon-sm" /> : <ImagePlus />}
                  {t("elements.saveAndInsert")}
                </Button>
              </div>
            </div>
          </section>

          <section className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                {t("elements.listTitle")}
              </h3>
              <div className="flex items-center gap-2">
                <Languages
                  className="size-icon-sm text-muted-foreground"
                  aria-hidden="true"
                />
                <Select
                  value={languageValue}
                  onValueChange={setLanguageValue}
                  disabled={!capabilities?.available || languageOptions.length === 0}
                >
                  <SelectTrigger
                    className="h-7 w-auto max-w-40 px-2 text-2xs"
                    aria-label={t("elements.text.language")}
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {languageOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Badge variant="outline">{elements.length}</Badge>
              </div>
            </div>

            {elementsQuery.isLoading ? (
              <div className="flex items-center justify-center py-6">
                <Spinner className="size-icon-lg text-primary" />
                <span className="sr-only">{tCommon("loading")}</span>
              </div>
            ) : elementsQuery.isError ? (
              <EmptyState
                compact
                icon={CircleAlert}
                title={t("elements.loadError.title")}
                description={t("elements.loadError.description")}
                action={
                  <Button variant="outline" size="sm" onClick={() => void elementsQuery.refetch()}>
                    {tCommon("actions.retry")}
                  </Button>
                }
              />
            ) : elements.length === 0 ? (
              <EmptyState
                compact
                icon={ScanSearch}
                title={t("elements.empty.title")}
                description={t("elements.empty.description")}
              />
            ) : (
              elements.map((element) => {
                const url = api.assetUrl(projectId, element.asset_id, element.updated_at);
                return (
                  <article
                    key={element.id}
                    className="flex gap-3 rounded-lg border border-border/70 bg-background/50 p-2.5 shadow-xs"
                  >
                    <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-md border border-border/60 bg-muted/30">
                      {url ? (
                        <img
                          src={url}
                          alt=""
                          className="max-h-full max-w-full object-contain"
                          loading="lazy"
                          draggable={false}
                        />
                      ) : (
                        <ImagePlus className="size-icon-lg text-muted-foreground" />
                      )}
                    </div>

                    <div className="min-w-0 flex-1 space-y-1.5">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant="outline">{t(`elements.kind.${element.kind}`)}</Badge>
                        <Badge variant={element.verified ? "success" : "outline"}>
                          {element.verified
                            ? t("elements.verified")
                            : t("elements.unverified")}
                        </Badge>
                        {element.stale ? (
                          <Badge variant="warning">{t("elements.stale")}</Badge>
                        ) : null}
                        <span className="font-mono text-2xs text-muted-foreground">
                          {t("elements.regionSize", {
                            width: element.width,
                            height: element.height,
                          })}
                        </span>
                      </div>

                      {editingId === element.id ? (
                        <div className="flex items-center gap-1">
                          <Input
                            value={captionDraft}
                            maxLength={500}
                            autoFocus
                            aria-label={t("elements.caption")}
                            className="h-7 px-2 text-xs"
                            onChange={(event) => setCaptionDraft(event.target.value)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter") {
                                event.preventDefault();
                                saveCaption(element.id);
                              } else if (event.key === "Escape") {
                                event.preventDefault();
                                setEditingId(null);
                              }
                            }}
                          />
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            aria-label={tCommon("actions.save")}
                            onClick={() => saveCaption(element.id)}
                            disabled={updateElement.isPending}
                          >
                            <Check />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            aria-label={tCommon("actions.cancel")}
                            onClick={() => setEditingId(null)}
                          >
                            <X />
                          </Button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1">
                          <p className="min-w-0 flex-1 truncate text-xs">
                            {element.caption || (
                              <span className="italic text-muted-foreground">
                                {t("elements.noCaption")}
                              </span>
                            )}
                          </p>
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            aria-label={t("elements.editCaption")}
                            onClick={() => startCaptionEdit(element.id, element.caption)}
                          >
                            <Pencil />
                          </Button>
                        </div>
                      )}

                      {editingTextId === element.id ? (
                        <div className="space-y-1.5 rounded-md border border-border/60 bg-muted/20 p-2">
                          <Textarea
                            value={textDraft}
                            autoFocus
                            maxLength={20_000}
                            aria-label={t("elements.text.editLabel")}
                            className="min-h-20 text-xs"
                            onChange={(event) => setTextDraft(event.target.value)}
                            onKeyDown={(event) => {
                              if (event.key === "Escape") {
                                event.preventDefault();
                                setEditingTextId(null);
                              }
                            }}
                          />
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setEditingTextId(null)}
                            >
                              {tCommon("actions.cancel")}
                            </Button>
                            <Button
                              size="sm"
                              className="gap-1"
                              onClick={() => saveText(element.id)}
                              disabled={updateText.isPending}
                            >
                              {updateText.isPending ? (
                                <Spinner className="size-icon-sm" />
                              ) : (
                                <Check />
                              )}
                              {tCommon("actions.save")}
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div className="rounded-md border border-border/60 bg-muted/20 p-2">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                              {t("elements.text.title")}
                            </span>
                            {element.text ? (
                              <>
                                {element.text_corrected ? (
                                  <Badge variant="outline">
                                    {t("elements.text.corrected")}
                                  </Badge>
                                ) : (
                                  <Badge
                                    variant={confidenceVariant(
                                      element.text_confidence,
                                    )}
                                  >
                                    {t("elements.text.confidence", {
                                      value:
                                        element.text_confidence === null
                                          ? "—"
                                          : Math.round(element.text_confidence),
                                    })}
                                  </Badge>
                                )}
                                {element.text_languages.length > 0 ? (
                                  <Badge variant="outline">
                                    {element.text_languages
                                      .map((code) => languageLabel(code, t))
                                      .join(" + ")}
                                  </Badge>
                                ) : null}
                              </>
                            ) : null}
                            <span className="ml-auto flex items-center gap-0.5">
                              <Button
                                variant="ghost"
                                size="icon-xs"
                                aria-label={t("elements.text.edit")}
                                onClick={() =>
                                  startTextEdit(element.id, element.text)
                                }
                              >
                                <Pencil />
                              </Button>
                              {element.text ? (
                                <Button
                                  variant="ghost"
                                  size="icon-xs"
                                  aria-label={t("elements.text.insert")}
                                  onClick={() => insertElementText(element.id)}
                                >
                                  <Pilcrow />
                                </Button>
                              ) : null}
                              <Button
                                variant="ghost"
                                size="sm"
                                className="gap-1"
                                onClick={() => extractElementText(element.id)}
                                disabled={
                                  !capabilities?.available ||
                                  extractingId === element.id
                                }
                              >
                                {extractingId === element.id ? (
                                  <Spinner className="size-icon-sm" />
                                ) : (
                                  <ScanText />
                                )}
                                {element.text_engine
                                  ? t("elements.text.reread")
                                  : t("elements.text.read")}
                              </Button>
                            </span>
                          </div>
                          {element.text ? (
                            <p className="scrollbar-thin mt-1.5 max-h-28 overflow-y-auto whitespace-pre-wrap text-xs leading-relaxed">
                              {element.text}
                            </p>
                          ) : (
                            <p className="mt-1.5 text-2xs italic leading-relaxed text-muted-foreground">
                              {capabilities && !capabilities.available
                                ? t("elements.text.unavailable")
                                : element.text_engine
                                  ? t("elements.text.noTextDetected")
                                  : t("elements.text.empty")}
                            </p>
                          )}
                        </div>
                      )}

                      <div className="flex flex-wrap items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="gap-1"
                          onClick={() => insertSaved(element.id)}
                        >
                          <ImagePlus />
                          {t("elements.insert")}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="gap-1"
                          onClick={() => toggleVerified(element.id, !element.verified)}
                          disabled={updateElement.isPending}
                        >
                          <CheckCheck />
                          {element.verified ? t("elements.unverify") : t("elements.verify")}
                        </Button>
                        {deleteId === element.id ? (
                          <span className="flex items-center gap-1">
                            <span className="text-2xs text-muted-foreground">
                              {t("elements.confirmDelete")}
                            </span>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="gap-1 text-destructive hover:bg-destructive/10"
                              onClick={() => remove(element.id)}
                              disabled={deleteElement.isPending}
                            >
                              <Trash2 />
                              {tCommon("actions.delete")}
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon-xs"
                              aria-label={tCommon("actions.cancel")}
                              onClick={() => setDeleteId(null)}
                            >
                              <X />
                            </Button>
                          </span>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            className={cn("gap-1 text-muted-foreground")}
                            onClick={() => setDeleteId(element.id)}
                          >
                            <Trash2 />
                            {tCommon("actions.delete")}
                          </Button>
                        )}
                      </div>
                    </div>
                  </article>
                );
              })
            )}
          </section>
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
