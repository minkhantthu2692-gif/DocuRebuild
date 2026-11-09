import {
  Check,
  CircleAlert,
  Copy,
  ExternalLink,
  Play,
  RefreshCw,
  ScanText,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type { OcrBlock, OcrBlockKind, PageSummary } from "@docurebuild/shared-types";

import { Badge, type BadgeProps } from "@/components/ui/badge";
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
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/input";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useOcrCapabilities, useLatestOcr, useStartOcr, useUpdateOcrBlock } from "@/hooks/use-ocr";
import { formatDateTime, resolveLocale } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useWorkspaceActions } from "./workspace-actions-context";

interface OcrDialogProps {
  projectId: string;
  page: PageSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInserted?: () => void;
}

const TESSERACT_GUIDE = "https://tesseract-ocr.github.io/tessdoc/Installation.html";

function confidenceVariant(value: number | null): NonNullable<BadgeProps["variant"]> {
  if (value === null) return "outline";
  if (value >= 85) return "success";
  if (value >= 60) return "warning";
  return "destructive";
}

function languageLabel(code: string, t: (key: string) => string): string {
  if (code === "eng") return t("ocr.languageEnglish");
  if (code === "mya") return t("ocr.languageBurmese");
  return code;
}

export function OcrDialog({
  projectId,
  page,
  open,
  onOpenChange,
  onInserted,
}: OcrDialogProps) {
  const { t, i18n } = useTranslation("workspace");
  const { t: tErrors } = useTranslation("errors");
  const { t: tCommon } = useTranslation("common");
  const locale = resolveLocale(i18n.resolvedLanguage);
  const errorMessage = useApiErrorMessage();
  const { insertText } = useWorkspaceActions();

  const capabilitiesQuery = useOcrCapabilities();
  const capabilities = capabilitiesQuery.data;
  const latestQuery = useLatestOcr(projectId, page?.id ?? null, open);
  const startOcr = useStartOcr(projectId);
  const updateBlock = useUpdateOcrBlock(projectId);

  const [languageValue, setLanguageValue] = useState("eng");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [includeNote, setIncludeNote] = useState(true);
  const initializedRun = useRef<string | null>(null);

  const run = latestQuery.data ?? null;
  const blocks = run?.blocks ?? [];
  const busy = startOcr.isPending || run?.status === "queued" || run?.status === "running";

  const languageOptions = useMemo(() => {
    if (!capabilities) return [];
    const installed = new Set(capabilities.languages);
    const options: Array<{ value: string; label: string }> = [];
    if (installed.has("eng")) {
      options.push({ value: "eng", label: t("ocr.languageEnglish") });
    }
    if (installed.has("mya")) {
      options.push({ value: "mya", label: t("ocr.languageBurmese") });
    }
    if (installed.has("eng") && installed.has("mya")) {
      options.push({ value: "eng+mya", label: t("ocr.languageMixed") });
    }
    for (const code of capabilities.languages) {
      if (code !== "eng" && code !== "mya") {
        options.push({ value: code, label: code });
      }
    }
    return options;
  }, [capabilities, t]);

  useEffect(() => {
    if (!open) {
      initializedRun.current = null;
      return;
    }
    if (!capabilities) return;
    setLanguageValue((current) => {
      if (languageOptions.some((option) => option.value === current)) return current;
      if (languageOptions.some((option) => option.value === "eng")) return "eng";
      return languageOptions[0]?.value ?? "eng";
    });
  }, [open, capabilities, languageOptions]);

  useEffect(() => {
    if (!open) {
      initializedRun.current = null;
      return;
    }
    if (!run) {
      initializedRun.current = null;
      setDrafts({});
      setSelected({});
      return;
    }
    const key = `${run.id}:${run.status}:${run.blocks.length}`;
    if (initializedRun.current === key) return;
    initializedRun.current = key;
    setDrafts(Object.fromEntries(run.blocks.map((block) => [block.id, block.text])));
    setSelected(Object.fromEntries(run.blocks.map((block) => [block.id, true])));
  }, [open, run]);

  const selectedBlocks = blocks.filter((block) => selected[block.id] ?? true);
  const dirtyBlocks = blocks.filter(
    (block) => (drafts[block.id] ?? block.text) !== block.text,
  );
  const allSelected = blocks.length > 0 && selectedBlocks.length === blocks.length;
  const runError =
    run?.error_code && i18n.exists(run.error_code, { ns: "errors" })
      ? tErrors(run.error_code)
      : run?.error || t("ocr.failed");

  const reasonKey =
    capabilities?.reason &&
    ["not_configured", "not_found", "not_executable", "no_languages", "error"].includes(
      capabilities.reason,
    )
      ? capabilities.reason
      : "error";

  const combinedText = selectedBlocks
    .map((block) => drafts[block.id] ?? block.text)
    .join("\n\n");

  const handleStart = () => {
    if (!page || !capabilities?.available) return;
    const languages = languageValue.split("+").filter(Boolean);
    startOcr.mutate(
      { pageId: page.id, languages },
      { onError: (error) => toast.error(errorMessage(error)) },
    );
  };

  const saveCorrections = async (silent = false): Promise<boolean> => {
    if (!page || dirtyBlocks.length === 0) return true;
    try {
      for (const block of dirtyBlocks) {
        await updateBlock.mutateAsync({
          pageId: page.id,
          blockId: block.id,
          text: drafts[block.id] ?? block.text,
        });
      }
      if (!silent) toast.success(t("ocr.saved"));
      return true;
    } catch (error) {
      toast.error(errorMessage(error));
      return false;
    }
  };

  const toggleVerified = (block: OcrBlock, value: boolean) => {
    if (!page || run?.stale) return;
    updateBlock.mutate(
      { pageId: page.id, blockId: block.id, verified: value },
      { onError: (error) => toast.error(errorMessage(error)) },
    );
  };

  const handleInsert = async () => {
    if (!page || !run || run.stale) return;
    if (selectedBlocks.length === 0 || !combinedText.trim()) {
      toast.error(t("ocr.noSelection"));
      return;
    }
    const saved = await saveCorrections(true);
    if (!saved) return;
    const confidences = selectedBlocks
      .map((block) => block.confidence)
      .filter((value): value is number => value !== null);
    const confidence =
      confidences.length > 0
        ? Math.round(confidences.reduce((sum, value) => sum + value, 0) / confidences.length)
        : null;
    const allVerified = selectedBlocks.every(
      (block) => block.verified && (drafts[block.id] ?? block.text) === block.text,
    );
    const note = includeNote
      ? t("ocr.sourceNote", {
          page: page.page_number,
          confidence: confidence ?? "—",
          status: allVerified ? t("ocr.verified") : t("ocr.unverified"),
        })
      : null;
    insertText(combinedText, note);
    toast.success(t("ocr.inserted"));
    onOpenChange(false);
    onInserted?.();
  };

  const handleCopy = async () => {
    if (!combinedText.trim()) return;
    try {
      await navigator.clipboard.writeText(combinedText);
      toast.success(t("ocr.copied"));
    } catch {
      toast.error(t("ocr.copyFailed"));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] max-w-3xl flex-col gap-4 overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ScanText className="size-icon-sm text-primary" aria-hidden="true" />
            {t("ocr.title", { page: page?.page_number ?? "—" })}
          </DialogTitle>
          <DialogDescription>{t("ocr.description")}</DialogDescription>
        </DialogHeader>

        {capabilitiesQuery.isLoading ? (
          <div className="flex items-center justify-center py-10">
            <Spinner className="size-icon-lg text-primary" />
            <span className="sr-only">{tCommon("loading")}</span>
          </div>
        ) : capabilitiesQuery.isError ? (
          <EmptyState
            compact
            icon={CircleAlert}
            title={t("ocr.unavailable.title")}
            description={errorMessage(capabilitiesQuery.error)}
            action={
              <Button
                variant="outline"
                size="sm"
                onClick={() => void capabilitiesQuery.refetch()}
              >
                {t("ocr.refresh")}
              </Button>
            }
          />
        ) : capabilities ? (
          <>
            {capabilities.available ? (
              <>
                <div className="flex flex-col gap-2 rounded-lg border border-border/70 bg-background/45 p-3 sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1 space-y-1">
                <label className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t("ocr.language")}
                </label>
                <Select
                  value={languageValue}
                  onValueChange={setLanguageValue}
                  disabled={busy || languageOptions.length === 0}
                >
                  <SelectTrigger className="h-control" aria-label={t("ocr.language")}>
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
              </div>
              <div className="flex shrink-0 flex-col items-stretch gap-1 sm:items-end">
                <Button
                  size="sm"
                  className="gap-1.5"
                  onClick={handleStart}
                  disabled={busy || languageOptions.length === 0}
                >
                  {busy ? <Spinner className="size-icon-sm" /> : run ? <RefreshCw /> : <Play />}
                  {busy
                    ? t("ocr.running")
                    : run
                      ? t("ocr.rerun")
                      : t("ocr.run")}
                </Button>
                <span className="text-center text-2xs text-muted-foreground sm:text-right">
                  {run ? t(`ocr.status.${run.status}`) : t("ocr.notRun")}
                </span>
              </div>
            </div>

                <div className="flex gap-2 rounded-lg border border-border/60 bg-background/50 p-3 text-2xs leading-relaxed text-muted-foreground">
                  <CircleAlert className="mt-0.5 size-icon-sm shrink-0 text-warning" aria-hidden="true" />
                  <p>{t("ocr.reviewNote")}</p>
                </div>
              </>
            ) : (
              <div className="space-y-3">
                <EmptyState
                  compact
                  icon={ScanText}
                  title={t("ocr.unavailable.title")}
                  description={t(`ocr.unavailable.${reasonKey}`)}
                />
                <div className="rounded-lg border border-border/70 bg-muted/35 p-3 text-2xs leading-relaxed text-muted-foreground">
                  <p>{t("ocr.setupHint")}</p>
                  {capabilities.setup_hint ? (
                    <p className="mt-1.5 font-mono text-2xs">{capabilities.setup_hint}</p>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5"
                    onClick={() => void capabilitiesQuery.refetch()}
                  >
                    <RefreshCw />
                    {t("ocr.refresh")}
                  </Button>
                  <Button asChild variant="ghost" size="sm" className="gap-1.5">
                    <a href={TESSERACT_GUIDE} target="_blank" rel="noreferrer">
                      <ExternalLink />
                      {t("ocr.setupGuide")}
                    </a>
                  </Button>
                </div>
              </div>
            )}

            {capabilities.available || run ? (
              <div className="scrollbar-thin -mx-1 min-h-0 flex-1 space-y-3 overflow-y-auto px-1">
              {latestQuery.isLoading ? (
                <div className="flex items-center justify-center py-10">
                  <Spinner className="size-icon-lg text-primary" />
                  <span className="sr-only">{tCommon("loading")}</span>
                </div>
              ) : latestQuery.isError ? (
                <EmptyState
                  compact
                  icon={CircleAlert}
                  title={t("ocr.loadError.title")}
                  description={t("ocr.loadError.description")}
                  action={
                    <Button variant="outline" size="sm" onClick={() => void latestQuery.refetch()}>
                      {tCommon("actions.retry")}
                    </Button>
                  }
                />
              ) : run ? (
                <>
                  {run.stale ? (
                    <div className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-2xs leading-relaxed">
                      <p className="font-semibold text-warning">{t("ocr.stale.title")}</p>
                      <p className="mt-0.5 text-muted-foreground">{t("ocr.stale.description")}</p>
                    </div>
                  ) : null}

                  {run.status === "failed" ? (
                    <EmptyState
                      compact
                      icon={CircleAlert}
                      title={t("ocr.failed")}
                      description={runError}
                    />
                  ) : run.status === "succeeded" ? (
                    <>
                      <div className="flex flex-wrap items-center gap-1.5 text-2xs text-muted-foreground">
                        <Badge variant="outline">
                          {t("ocr.engine")}: {run.engine}
                          {run.engine_version ? ` ${run.engine_version}` : ""}
                        </Badge>
                        <Badge variant="outline">
                          {run.languages.map((code) => languageLabel(code, t)).join(" + ")}
                        </Badge>
                        <Badge variant={confidenceVariant(run.mean_confidence)}>
                          {t("ocr.meanConfidence", {
                            value:
                              run.mean_confidence === null
                                ? "—"
                                : Math.round(run.mean_confidence),
                          })}
                        </Badge>
                        <span>
                          {formatDateTime(run.completed_at ?? run.created_at, locale)}
                        </span>
                      </div>

                      {blocks.length === 0 ? (
                        <EmptyState
                          compact
                          icon={ScanText}
                          title={t("ocr.noText.title")}
                          description={t("ocr.noText.description")}
                        />
                      ) : (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between gap-2">
                            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                              {t("ocr.blocks")}
                            </h3>
                            <label className="flex items-center gap-1.5 text-2xs text-muted-foreground">
                              <input
                                type="checkbox"
                                className="size-3.5 accent-primary"
                                checked={allSelected}
                                onChange={(event) => {
                                  const checked = event.target.checked;
                                  setSelected(
                                    Object.fromEntries(
                                      blocks.map((block) => [block.id, checked]),
                                    ),
                                  );
                                }}
                              />
                              {t("ocr.selectAll")}
                            </label>
                          </div>

                          {blocks.map((block) => {
                            const draft = drafts[block.id] ?? block.text;
                            const dirty = draft !== block.text;
                            return (
                              <article
                                key={block.id}
                                className="rounded-lg border border-border/70 bg-background/50 p-3 shadow-xs"
                              >
                                <div className="flex flex-wrap items-center gap-1.5">
                                  <label className="flex items-center gap-1.5 text-2xs">
                                    <input
                                      type="checkbox"
                                      className="size-3.5 accent-primary"
                                      checked={selected[block.id] ?? true}
                                      onChange={(event) =>
                                        setSelected((current) => ({
                                          ...current,
                                          [block.id]: event.target.checked,
                                        }))
                                      }
                                      aria-label={t("ocr.selectBlock", {
                                        index: block.block_index,
                                      })}
                                    />
                                    <span className="font-mono text-muted-foreground">
                                      #{block.block_index}
                                    </span>
                                  </label>
                                  <Badge variant="secondary">
                                    {t(`ocr.kind.${block.kind as OcrBlockKind}`)}
                                  </Badge>
                                  <Badge variant={confidenceVariant(block.confidence)}>
                                    {block.confidence === null
                                      ? "—"
                                      : `${Math.round(block.confidence)}%`}
                                  </Badge>
                                  <Badge variant={block.verified ? "success" : "warning"}>
                                    {block.verified ? t("ocr.verified") : t("ocr.unverified")}
                                  </Badge>
                                  {block.corrected ? (
                                    <Badge variant="outline">{t("ocr.corrected")}</Badge>
                                  ) : null}
                                  <label
                                    className={cn(
                                      "ml-auto flex items-center gap-1.5 text-2xs",
                                      dirty && "opacity-50",
                                    )}
                                  >
                                    <input
                                      type="checkbox"
                                      className="size-3.5 accent-primary"
                                      checked={block.verified}
                                      disabled={dirty || updateBlock.isPending || run.stale}
                                      onChange={(event) =>
                                        toggleVerified(block, event.target.checked)
                                      }
                                    />
                                    {t("ocr.markVerified")}
                                  </label>
                                </div>
                                <Textarea
                                  value={draft}
                                  dir="auto"
                                  rows={Math.min(6, Math.max(2, block.line_count))}
                                  onChange={(event) =>
                                    setDrafts((current) => ({
                                      ...current,
                                      [block.id]: event.target.value,
                                    }))
                                  }
                                  aria-label={t("ocr.block", { index: block.block_index })}
                                  className="mt-2 font-document text-sm leading-relaxed"
                                />
                                {dirty ? (
                                  <p className="mt-1 text-2xs text-warning">
                                    {t("ocr.unsavedCorrection")}
                                  </p>
                                ) : null}
                              </article>
                            );
                          })}
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center text-xs text-muted-foreground" role="status" aria-live="polite">
                      <Spinner className="size-icon-lg text-primary" />
                      <p>{run.status === "queued" ? t("ocr.queued") : t("ocr.running")}</p>
                    </div>
                  )}
                </>
              ) : (
                <EmptyState
                  compact
                  icon={ScanText}
                  title={t("ocr.notRunTitle")}
                  description={t("ocr.notRunDescription")}
                />
              )}
              </div>
            ) : null}

            <DialogFooter className="mt-0 shrink-0 items-stretch gap-2 border-t border-border/60 pt-3 sm:items-center">
              <label className="mr-auto flex items-center gap-1.5 text-2xs text-muted-foreground sm:mr-auto">
                <input
                  type="checkbox"
                  className="size-3.5 accent-primary"
                  checked={includeNote}
                  onChange={(event) => setIncludeNote(event.target.checked)}
                  disabled={!run || run.stale}
                />
                {t("ocr.insertNote")}
              </label>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                {tCommon("actions.close")}
              </Button>
              {run?.status === "succeeded" && !run.stale ? (
                <>
                  {dirtyBlocks.length > 0 ? (
                    <Button
                      variant="outline"
                      disabled={updateBlock.isPending}
                      onClick={() => void saveCorrections()}
                    >
                      {t("ocr.saveCorrections")}
                    </Button>
                  ) : null}
                  <Button
                    variant="outline"
                    className="gap-1.5"
                    onClick={() => void handleCopy()}
                    disabled={selectedBlocks.length === 0}
                  >
                    <Copy />
                    {t("ocr.copy")}
                  </Button>
                  <Button
                    className="gap-1.5"
                    onClick={() => void handleInsert()}
                    disabled={selectedBlocks.length === 0 || updateBlock.isPending}
                  >
                    <Check />
                    {t("ocr.insertSelected")}
                  </Button>
                </>
              ) : null}
            </DialogFooter>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
