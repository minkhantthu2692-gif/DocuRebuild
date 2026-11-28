import {
  Check,
  CircleAlert,
  Copy,
  ExternalLink,
  Play,
  RefreshCw,
  ScanText,
  Sigma,
  Sparkles,
  Table2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import type { AiSuggestion, ElementSummary, OcrBlock, OcrBlockKind, PageSummary } from "@docurebuild/shared-types";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import {
  useAiTasks,
  useCreateAiSuggestion,
  useDecideAiSuggestion,
  usePageAiSuggestionHistory,
  usePageAiSuggestions,
} from "@/hooks/use-ai";
import { useAppMeta } from "@/hooks/use-app";
import { useOcrCapabilities, useLatestOcr, useStartOcr, useUpdateOcrBlock } from "@/hooks/use-ocr";
import { formatDateTime, resolveLocale } from "@/lib/format";
import {
  buildLanguageOptions,
  confidenceVariant,
  languageLabel,
  preferredSegmentationMode,
} from "@/lib/ocr-display";
import { cn } from "@/lib/utils";
import { PageEquationsDialog } from "./page-equations-dialog";
import { PageTablesDialog } from "./page-tables-dialog";
import { usePaidAiGuard } from "./paid-ai-confirm-dialog";
import { ProposalDiff } from "./proposal-diff";
import { RegionFormulaDialog } from "./region-formula-dialog";
import { TableProposalDialog } from "./table-proposal-dialog";
import { useWorkspaceActions } from "./workspace-actions-context";

interface OcrDialogProps {
  projectId: string;
  page: PageSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInserted?: () => void;
}

const TESSERACT_GUIDE = "https://tesseract-ocr.github.io/tessdoc/Installation.html";

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
  const metaQuery = useAppMeta();
  const tasksQuery = useAiTasks();
  const latestQuery = useLatestOcr(projectId, page?.id ?? null, open);
  const startOcr = useStartOcr(projectId);
  const updateBlock = useUpdateOcrBlock(projectId);
  const createSuggestion = useCreateAiSuggestion(projectId);
  const decideSuggestion = useDecideAiSuggestion(projectId);
  const suggestionsQuery = usePageAiSuggestions(projectId, page?.id ?? null, open);
  const historyQuery = usePageAiSuggestionHistory(projectId, page?.id ?? null, open);
  const paidAi = usePaidAiGuard();

  const [languageValue, setLanguageValue] = useState("eng");
  const [segmentation, setSegmentation] = useState("3");
  const layoutChosen = useRef(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [includeNote, setIncludeNote] = useState(true);
  const [tableBlock, setTableBlock] = useState<OcrBlock | null>(null);
  const [tablesOpen, setTablesOpen] = useState(false);
  const [equationsOpen, setEquationsOpen] = useState(false);
  const [formulaElement, setFormulaElement] = useState<ElementSummary | null>(
    null,
  );
  const [formulaText, setFormulaText] = useState("");
  const initializedRun = useRef<string | null>(null);

  const run = latestQuery.data ?? null;
  const blocks = useMemo(() => run?.blocks ?? [], [run]);
  const busy = startOcr.isPending || run?.status === "queued" || run?.status === "running";
  const aiAvailable = metaQuery.data?.capabilities.ai === true;
  const cleanupTask = tasksQuery.data?.tasks.ocr_cleanup;
  const aiConfigured = aiAvailable && cleanupTask?.configured === true;

  const languageOptions = useMemo(
    () => buildLanguageOptions(capabilities?.languages, t),
    [capabilities, t],
  );

  // Pages in a script whose line spacing confuses automatic layout analysis
  // (Burmese) get sparse-text segmentation. The choice is visible in the
  // selector, and any manual choice stops this from overriding it.
  useEffect(() => {
    if (!capabilities || layoutChosen.current) return;
    setSegmentation(
      String(preferredSegmentationMode(languageValue, capabilities.page_segmentation_mode)),
    );
  }, [capabilities, languageValue]);

  useEffect(() => {
    if (!open) {
      initializedRun.current = null;
      setTableBlock(null);
      setTablesOpen(false);
      setEquationsOpen(false);
      setFormulaElement(null);
      setFormulaText("");
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
  const someSelected = !allSelected && selectedBlocks.length > 0;
  const runError =
    run?.error_code && i18n.exists(run.error_code, { ns: "errors" })
      ? tErrors(run.error_code)
      : run?.error || t("ocr.failed");
  const embeddedText = run?.engine === "pdf-text";

  const suggestions = useMemo(() => {
    const blockIds = new Set(blocks.map((block) => block.id));
    return Object.fromEntries(
      (suggestionsQuery.data?.suggestions ?? [])
        .filter((suggestion) => blockIds.has(suggestion.block_id))
        .map((suggestion) => [suggestion.block_id, suggestion]),
    ) as Record<string, AiSuggestion>;
  }, [blocks, suggestionsQuery.data]);

  const proposalHistory = useMemo(() => {
    const blockIds = new Set(blocks.map((block) => block.id));
    const grouped: Record<string, AiSuggestion[]> = {};
    (historyQuery.data?.suggestions ?? []).forEach((suggestion) => {
      if (suggestion.status === "pending") return;
      if (!blockIds.has(suggestion.block_id)) return;
      (grouped[suggestion.block_id] ??= []).push(suggestion);
    });
    return grouped;
  }, [blocks, historyQuery.data]);

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
      {
        pageId: page.id,
        languages,
        pageSegmentationMode: Number(segmentation),
      },
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

  const requestAiCleanup = async (block: OcrBlock) => {
    if (!page || !run || run.stale || !aiConfigured) return;
    // A paid route is approved per action, before anything is sent.
    const approved = await paidAi.requestApproval(cleanupTask);
    if (!approved) return;
    // The proposal must describe the text that is actually stored, so pending
    // local corrections are saved before the request.
    const saved = await saveCorrections(true);
    if (!saved) return;
    createSuggestion.mutate(
      { pageId: page.id, blockId: block.id, payload: { confirm_paid: true } },
      { onError: (error) => toast.error(errorMessage(error)) },
    );
  };

  const decideProposal = (suggestion: AiSuggestion, status: "accepted" | "rejected") => {
    decideSuggestion.mutate(
      { suggestionId: suggestion.id, payload: { status } },
      {
        onSuccess: (response) => {
          if (status === "accepted") {
            // Let the updated block text from the server become the draft.
            setDrafts((current) => {
              const next = { ...current };
              delete next[response.suggestion.block_id];
              return next;
            });
            toast.success(t("ocr.ai.accepted"));
          } else {
            toast.success(t("ocr.ai.rejected"));
          }
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
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
    insertText(
      combinedText,
      note,
      selectedBlocks.map((block) => ({
        kind: block.kind,
        text: drafts[block.id] ?? block.text,
        x: block.x,
        y: block.y,
        width: block.width,
        height: block.height,
        lines: block.lines,
      })),
    );
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
              <div className="min-w-0 flex-1 space-y-1">
                <label className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t("ocr.layout")}
                </label>
                <Select
                  value={segmentation}
                  onValueChange={(value) => {
                    layoutChosen.current = true;
                    setSegmentation(value);
                  }}
                  disabled={busy}
                >
                  <SelectTrigger className="h-control" aria-label={t("ocr.layout")}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="3">{t("ocr.layoutAuto")}</SelectItem>
                    <SelectItem value="4">{t("ocr.layoutColumn")}</SelectItem>
                    <SelectItem value="6">{t("ocr.layoutBlock")}</SelectItem>
                    <SelectItem value="11">{t("ocr.layoutSparse")}</SelectItem>
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
                  {busy ? <Spinner className="size-icon-sm" /> : run && !embeddedText ? <RefreshCw /> : <Play />}
                  {busy
                    ? t("ocr.running")
                    : run && !embeddedText
                      ? t("ocr.rerun")
                      : t("ocr.run")}
                </Button>
                <span className="text-center text-2xs text-muted-foreground sm:text-right">
                  {run ? t(`ocr.status.${run.status}`) : t("ocr.notRun")}
                </span>
              </div>
            </div>

                <p className="text-2xs text-muted-foreground">{t("ocr.layoutHint")}</p>

                <div className="flex gap-2 rounded-lg border border-border/60 bg-background/50 p-3 text-2xs leading-relaxed text-muted-foreground">
                  <CircleAlert className="mt-0.5 size-icon-sm shrink-0 text-warning" aria-hidden="true" />
                  <p>
                    {t(
                      embeddedText
                        ? "ocr.reviewNoteEmbedded"
                        : "ocr.reviewNote",
                    )}
                  </p>
                </div>

                {aiAvailable && !aiConfigured ? (
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-border/60 bg-background/50 p-3 text-2xs leading-relaxed text-muted-foreground">
                    <Sparkles className="size-icon-sm shrink-0 text-primary" aria-hidden="true" />
                    <p>
                      {t("ocr.ai.notConfigured")}{" "}
                      <Link
                        to="/settings#ai"
                        className="font-medium text-primary underline-offset-2 hover:underline"
                        onClick={() => onOpenChange(false)}
                      >
                        {t("ocr.ai.openSettings")}
                      </Link>
                    </p>
                  </div>
                ) : null}
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
                      <p className="font-semibold text-warning">
                        {t(
                          embeddedText
                            ? "ocr.stale.embeddedTitle"
                            : "ocr.stale.title",
                        )}
                      </p>
                      <p className="mt-0.5 text-muted-foreground">
                        {t(
                          embeddedText
                            ? "ocr.stale.embeddedDescription"
                            : "ocr.stale.description",
                        )}
                      </p>
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
                          {t("ocr.engine")}:{" "}
                          {embeddedText ? t("ocr.embeddedEngine") : run.engine}
                          {run.engine_version ? ` ${run.engine_version}` : ""}
                        </Badge>
                        {run.languages.length > 0 ? (
                          <Badge variant="outline">
                            {run.languages.map((code) => languageLabel(code, t)).join(" + ")}
                          </Badge>
                        ) : null}
                        {embeddedText ? (
                          <Badge variant="outline">{t("ocr.embeddedConfidence")}</Badge>
                        ) : (
                          <Badge variant={confidenceVariant(run.mean_confidence)}>
                            {t("ocr.meanConfidence", {
                              value:
                                run.mean_confidence === null
                                  ? "—"
                                  : Math.round(run.mean_confidence),
                            })}
                          </Badge>
                        )}
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
                            <div className="flex items-center gap-2">
                              <Button
                                variant="ghost"
                                size="sm"
                                className="gap-1.5"
                                onClick={() => setTablesOpen(true)}
                                disabled={run.stale}
                              >
                                <Table2 />
                                {t("ocr.table.detect")}
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="gap-1.5"
                                onClick={() => setEquationsOpen(true)}
                                disabled={run.stale}
                              >
                                <Sigma />
                                {t("ocr.equation.detect")}
                              </Button>
                              <label className="flex items-center gap-1.5 text-2xs text-muted-foreground">
                                <Checkbox
                                  checked={allSelected}
                                  indeterminate={someSelected}
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
                          </div>

                          {blocks.map((block) => {
                            const draft = drafts[block.id] ?? block.text;
                            const dirty = draft !== block.text;
                            const suggestion = suggestions[block.id];
                            const proposalStale = Boolean(
                              suggestion &&
                                (draft !== suggestion.original_text ||
                                  block.text !== suggestion.original_text),
                            );
                            const requestingThis =
                              createSuggestion.isPending &&
                              createSuggestion.variables?.blockId === block.id;
                            const history = proposalHistory[block.id] ?? [];
                            return (
                              <article
                                key={block.id}
                                className="rounded-lg border border-border/70 bg-background/50 p-3 shadow-xs"
                              >
                                <div className="flex flex-wrap items-center gap-1.5">
                                  <label className="flex items-center gap-1.5 text-2xs">
                                    <Checkbox
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
                                    <Checkbox
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

                                {block.kind === "table" ? (
                                  block.corrected ? (
                                    <p className="mt-2 text-2xs leading-relaxed text-muted-foreground">
                                      {t("ocr.table.correctedHint")}
                                    </p>
                                  ) : (
                                    <div className="mt-2 flex flex-wrap items-center justify-end gap-2">
                                      {dirty ? (
                                        <span className="text-2xs text-muted-foreground">
                                          {t("ocr.table.saveFirst")}
                                        </span>
                                      ) : null}
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        className="gap-1.5"
                                        disabled={run.stale || dirty}
                                        onClick={() => setTableBlock(block)}
                                      >
                                        <Table2 />
                                        {t("ocr.table.build")}
                                      </Button>
                                    </div>
                                  )
                                ) : null}

                                {suggestion ? (
                                  <div className="mt-2 rounded-lg border border-primary/30 bg-primary/5 p-2.5">
                                    <div className="flex flex-wrap items-center gap-1.5 text-2xs">
                                      <Sparkles className="size-icon-sm text-primary" aria-hidden="true" />
                                      <span className="font-medium">
                                        {t("ocr.ai.proposedBy", {
                                          provider: t(
                                            `ocr.ai.providers.${suggestion.provider}`,
                                          ),
                                          model: suggestion.model,
                                        })}
                                      </span>
                                      <Badge variant="warning">
                                        {t("ocr.ai.unverified")}
                                      </Badge>
                                    </div>
                                    <div className="mt-2">
                                      <ProposalDiff
                                        original={suggestion.original_text}
                                        proposed={suggestion.proposed_text}
                                        originalLabel={t("ocr.ai.original")}
                                        proposedLabel={t("ocr.ai.proposed")}
                                        documentFont
                                      />
                                    </div>
                                    <p
                                      className={cn(
                                        "mt-2 text-2xs leading-relaxed",
                                        proposalStale
                                          ? "text-warning"
                                          : "text-muted-foreground",
                                      )}
                                    >
                                      {proposalStale
                                        ? t("ocr.ai.stale")
                                        : t("ocr.ai.note")}
                                    </p>
                                    <div className="mt-2 flex flex-wrap justify-end gap-2">
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        className="gap-1.5"
                                        disabled={decideSuggestion.isPending}
                                        onClick={() =>
                                          decideProposal(suggestion, "rejected")
                                        }
                                      >
                                        <X />
                                        {t("ocr.ai.reject")}
                                      </Button>
                                      <Button
                                        size="sm"
                                        className="gap-1.5"
                                        disabled={
                                          proposalStale || decideSuggestion.isPending
                                        }
                                        onClick={() =>
                                          decideProposal(suggestion, "accepted")
                                        }
                                      >
                                        <Check />
                                        {t("ocr.ai.accept")}
                                      </Button>
                                    </div>
                                  </div>
                                ) : aiConfigured && block.text.trim() ? (
                                  <div className="mt-2 flex justify-end">
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      className="gap-1.5"
                                      disabled={run.stale || createSuggestion.isPending}
                                      onClick={() => void requestAiCleanup(block)}
                                    >
                                      {requestingThis ? (
                                        <Spinner className="size-icon-sm" />
                                      ) : (
                                        <Sparkles />
                                      )}
                                      {requestingThis
                                        ? t("ocr.ai.running")
                                        : t("ocr.ai.cleanup")}
                                    </Button>
                                  </div>
                                ) : null}

                                {history.length > 0 ? (
                                  <details className="mt-2 rounded-lg border border-border/60 bg-background/40 px-2.5 py-2">
                                    <summary className="cursor-pointer select-none text-2xs font-medium text-muted-foreground">
                                      {t("ocr.ai.history", { count: history.length })}
                                    </summary>
                                    <ul className="mt-2 space-y-2">
                                      {history.map((entry) => (
                                        <li
                                          key={entry.id}
                                          className="rounded-md border border-border/60 bg-background/50 p-2"
                                        >
                                          <div className="flex flex-wrap items-center gap-1.5 text-2xs">
                                            <Badge
                                              variant={
                                                entry.status === "accepted"
                                                  ? "success"
                                                  : "outline"
                                              }
                                            >
                                              {entry.status === "accepted"
                                                ? t("ocr.ai.historyAccepted")
                                                : t("ocr.ai.historyRejected")}
                                            </Badge>
                                            <span className="text-muted-foreground">
                                              {t(
                                                `ocr.ai.providers.${entry.provider}`,
                                              )}{" "}
                                              · {entry.model}
                                            </span>
                                            <span className="ml-auto text-muted-foreground">
                                              {formatDateTime(entry.updated_at, locale)}
                                            </span>
                                          </div>
                                          <details className="mt-1.5">
                                            <summary className="cursor-pointer select-none text-2xs text-muted-foreground">
                                              {t("ocr.ai.historyCompare")}
                                            </summary>
                                            <div className="mt-2">
                                              <ProposalDiff
                                                original={entry.original_text}
                                                proposed={entry.proposed_text}
                                                originalLabel={t("ocr.ai.original")}
                                                proposedLabel={t("ocr.ai.proposed")}
                                                mutedProposed
                                                documentFont
                                              />
                                            </div>
                                          </details>
                                        </li>
                                      ))}
                                    </ul>
                                  </details>
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
                <Checkbox
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
                    data-testid="ocr-insert"
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
      <TableProposalDialog
        projectId={projectId}
        page={page}
        block={tableBlock}
        open={Boolean(tableBlock)}
        onOpenChange={(next) => {
          if (!next) setTableBlock(null);
        }}
        onInserted={onInserted}
      />
      <PageTablesDialog
        projectId={projectId}
        page={page}
        open={tablesOpen}
        onOpenChange={setTablesOpen}
        onInserted={onInserted}
      />
      <PageEquationsDialog
        projectId={projectId}
        page={page}
        open={equationsOpen}
        onOpenChange={setEquationsOpen}
        onReview={(element, text) => {
          setEquationsOpen(false);
          setFormulaElement(element);
          setFormulaText(text);
        }}
      />
      <RegionFormulaDialog
        projectId={projectId}
        element={formulaElement}
        pageNumber={page?.page_number ?? null}
        initialLatex={formulaText}
        open={formulaElement !== null}
        onOpenChange={(next) => {
          if (!next) {
            setFormulaElement(null);
            setFormulaText("");
          }
        }}
        onInserted={onInserted}
      />
      {paidAi.paidDialog}
    </Dialog>
  );
}
