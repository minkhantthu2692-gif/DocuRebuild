import {
  ArrowLeft,
  Brain,
  Check,
  ChevronRight,
  Copy,
  ExternalLink,
  HardDrive,
  Info,
  Languages,
  Palette,
  RefreshCw,
  ScanText,
  ShieldCheck,
  Type,
  type LucideIcon,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import type {
  AccentName,
  AiProfileSettings,
  AiProbeResponse,
  AiProviderKind,
  BlurLevel,
  Density,
  DocumentFont,
  FontSizePreset,
  LanguageCode,
  MotionPreference,
  RadiusStyle,
  ThemeMode,
} from "@docurebuild/shared-types";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Separator } from "@/components/ui/separator";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useAiProviders, useProbeAiProvider } from "@/hooks/use-ai";
import { useAppMeta, useAppSettings, useHealth, useUpdateSettings } from "@/hooks/use-app";
import { useOcrCapabilities } from "@/hooks/use-ocr";
import { formatNumber, resolveLocale } from "@/lib/format";
import { cn } from "@/lib/utils";

const ACCENTS: AccentName[] = [
  "indigo",
  "violet",
  "blue",
  "teal",
  "emerald",
  "amber",
  "rose",
];

const ROADMAP: Array<{
  key: string;
  status: "done" | "inProgress" | "planned";
}> = [
  { key: "foundation", status: "done" },
  { key: "import", status: "done" },
  { key: "pdf", status: "done" },
  { key: "processing", status: "inProgress" },
  { key: "ocr", status: "inProgress" },
  { key: "ai", status: "inProgress" },
  { key: "editor", status: "inProgress" },
  { key: "export", status: "planned" },
  { key: "history", status: "planned" },
];

const STATUS_VARIANT = {
  done: "success",
  inProgress: "warning",
  planned: "outline",
} as const;

const DEFAULT_AI_PROFILE: AiProfileSettings = {
  provider: "ollama",
  base_url: "",
  model: "",
};

interface SettingsSectionProps {
  id: string;
  icon: LucideIcon;
  title: string;
  children: ReactNode;
}

function SettingsSection({ id, icon: Icon, title, children }: SettingsSectionProps) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-heading`}
      className="glass-panel scroll-mt-24 rounded-xl p-4 shadow-sm sm:p-5"
    >
      <header className="mb-4 flex items-center gap-2">
        <span className="flex size-7 items-center justify-center rounded-md bg-primary/10 text-primary">
          <Icon className="size-icon-sm" aria-hidden="true" />
        </span>
        <h2 id={`${id}-heading`} className="text-sm font-semibold tracking-tight">
          {title}
        </h2>
      </header>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

interface SettingRowProps {
  title: string;
  description?: string;
  children: ReactNode;
  stacked?: boolean;
}

function SettingRow({ title, description, children, stacked = false }: SettingRowProps) {
  return (
    <div
      className={cn(
        "flex gap-2.5",
        stacked ? "flex-col" : "flex-col sm:flex-row sm:items-center sm:justify-between",
      )}
    >
      <div className="min-w-0 max-w-md space-y-0.5">
        <p className="text-sm font-medium leading-snug">{title}</p>
        {description ? (
          <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
        ) : null}
      </div>
      <div className={cn("shrink-0", stacked ? "w-full" : "w-full sm:w-80")}>{children}</div>
    </div>
  );
}

export function SettingsPage() {
  const { t, i18n } = useTranslation("settings");
  const { t: tCommon } = useTranslation("common");
  const settingsQuery = useAppSettings();
  const metaQuery = useAppMeta();
  const healthQuery = useHealth();
  const ocrQuery = useOcrCapabilities();
  const aiProvidersQuery = useAiProviders();
  const probeAi = useProbeAiProvider();
  const updateSettings = useUpdateSettings();
  const errorMessage = useApiErrorMessage();
  const [copied, setCopied] = useState(false);
  const [aiDraftOverride, setAiDraftOverride] = useState<AiProfileSettings | null>(null);
  const [probeResult, setProbeResult] = useState<AiProbeResponse | null>(null);

  const settings = settingsQuery.data;
  const appearance = settings?.appearance;
  const language = settings?.language ?? "en";
  const documentFont = settings?.editor.document_font ?? "serif";
  const locale = resolveLocale(i18n.resolvedLanguage);
  const health = healthQuery.data;
  const ocr = ocrQuery.data;

  const aiSaved = settings?.ai?.text ?? DEFAULT_AI_PROFILE;
  const aiDraft = aiDraftOverride ?? aiSaved;
  const aiDirty =
    aiDraft.provider !== aiSaved.provider ||
    aiDraft.base_url !== aiSaved.base_url ||
    aiDraft.model !== aiSaved.model;
  const providerDefault =
    aiProvidersQuery.data?.providers.find((item) => item.id === aiDraft.provider)
      ?.default_base_url ?? "";
  const discoveredModels = probeResult?.status === "ready" ? probeResult.models : [];

  const updateAiDraft = (patch: Partial<AiProfileSettings>) => {
    setAiDraftOverride({ ...aiDraft, ...patch });
  };

  const ocrReason =
    ocr?.reason &&
    ["not_configured", "not_found", "not_executable", "no_languages", "error"].includes(
      ocr.reason,
    )
      ? ocr.reason
      : "error";

  const change = (patch: Parameters<typeof updateSettings.mutate>[0]) => {
    updateSettings.mutate(patch, {
      onError: (error) => toast.error(errorMessage(error)),
    });
  };

  const testAiConnection = () => {
    probeAi.mutate(
      { provider: aiDraft.provider, base_url: aiDraft.base_url },
      {
        onSuccess: (result) => setProbeResult(result),
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  };

  const saveAiProfile = () => {
    updateSettings.mutate(
      { ai: { text: aiDraft } },
      {
        onSuccess: () => {
          setAiDraftOverride(null);
          toast.success(t("ai.saved"));
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  };

  const sectionLinks: Array<{ id: string; label: string }> = [
    { id: "appearance", label: t("sections.appearance") },
    { id: "language", label: t("sections.language") },
    { id: "editor", label: t("sections.editor") },
    { id: "ocr", label: t("sections.ocr") },
    { id: "ai", label: t("sections.ai") },
    { id: "storage", label: t("sections.storage") },
    { id: "about", label: t("sections.about") },
  ];

  const copyPath = async () => {
    if (!health?.data_dir) return;
    try {
      await navigator.clipboard.writeText(health.data_dir);
      setCopied(true);
      toast.success(t("storage.copied"));
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error(t("storage.copyFailed"));
    }
  };

  return (
    <div className="scrollbar-thin scroll-smooth flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-content px-4 py-7 sm:px-6 lg:py-10">
        <header className="animate-slide-up">
          <Button asChild variant="ghost" size="sm" className="-ml-2 gap-1.5 text-muted-foreground">
            <Link to="/">
              <ArrowLeft />
              {t("backToProjects")}
            </Link>
          </Button>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">{t("title")}</h1>
          <p className="mt-1 max-w-xl text-sm leading-relaxed text-muted-foreground">
            {t("subtitle")}
          </p>
        </header>

        <div className="mt-7 grid gap-5 lg:grid-cols-[12rem_minmax(0,1fr)]">
          <nav aria-label={t("nav.label")} className="hidden lg:block">
            <div className="sticky top-6 space-y-0.5">
              {sectionLinks.map((section) => (
                <a
                  key={section.id}
                  href={`#${section.id}`}
                  className="focus-ring flex items-center justify-between rounded-md px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent/70 hover:text-foreground"
                >
                  {section.label}
                  <ChevronRight className="size-3 opacity-50" aria-hidden="true" />
                </a>
              ))}
            </div>
          </nav>

          <div className="space-y-4">
            <SettingsSection id="appearance" icon={Palette} title={t("sections.appearance")}>
              <SettingRow title={t("appearance.theme")} description={t("appearance.themeDescription")}>
                <SegmentedControl
                  label={t("appearance.theme")}
                  value={appearance?.theme ?? "system"}
                  onValueChange={(value) =>
                    change({ appearance: { theme: value as ThemeMode } })
                  }
                  options={[
                    { value: "system", label: tCommon("theme.system") },
                    { value: "light", label: tCommon("theme.light") },
                    { value: "dark", label: tCommon("theme.dark") },
                  ]}
                />
              </SettingRow>

              <Separator />

              <SettingRow
                stacked
                title={t("appearance.accent")}
                description={t("appearance.accentDescription")}
              >
                <div className="grid grid-cols-4 gap-2 sm:grid-cols-7">
                  {ACCENTS.map((accent) => {
                    const selected = (appearance?.accent ?? "indigo") === accent;
                    return (
                      <button
                        key={accent}
                        type="button"
                        aria-pressed={selected}
                        aria-label={t(`appearance.accentNames.${accent}`)}
                        onClick={() => change({ appearance: { accent } })}
                        className={cn(
                          "focus-ring flex flex-col items-center gap-1.5 rounded-lg border px-1 py-2 text-2xs transition-colors",
                          selected
                            ? "border-primary bg-primary/5 font-medium text-foreground"
                            : "border-border/70 text-muted-foreground hover:border-primary/40 hover:bg-accent/50",
                        )}
                      >
                        <span
                          className="accent-swatch flex size-6 items-center justify-center rounded-pill shadow-xs"
                          data-swatch={accent}
                        >
                          {selected ? (
                            <span className="flex size-3.5 items-center justify-center rounded-pill bg-background text-foreground">
                              <Check className="size-2.5" />
                            </span>
                          ) : null}
                        </span>
                        <span className="w-full truncate text-center">
                          {t(`appearance.accentNames.${accent}`)}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </SettingRow>

              <Separator />

              <SettingRow title={t("appearance.radius")} description={t("appearance.radiusDescription")}>
                <SegmentedControl
                  label={t("appearance.radius")}
                  value={appearance?.radius ?? "soft"}
                  onValueChange={(value) =>
                    change({ appearance: { radius: value as RadiusStyle } })
                  }
                  options={[
                    { value: "compact", label: t("appearance.radiusValues.compact") },
                    { value: "soft", label: t("appearance.radiusValues.soft") },
                    { value: "rounded", label: t("appearance.radiusValues.rounded") },
                  ]}
                />
              </SettingRow>

              <Separator />

              <SettingRow title={t("appearance.blur")} description={t("appearance.blurDescription")}>
                <SegmentedControl
                  label={t("appearance.blur")}
                  value={appearance?.blur ?? "subtle"}
                  onValueChange={(value) => change({ appearance: { blur: value as BlurLevel } })}
                  options={[
                    { value: "off", label: t("appearance.blurValues.off") },
                    { value: "subtle", label: t("appearance.blurValues.subtle") },
                    { value: "strong", label: t("appearance.blurValues.strong") },
                  ]}
                />
              </SettingRow>

              <Separator />

              <SettingRow
                title={t("appearance.density")}
                description={t("appearance.densityDescription")}
              >
                <SegmentedControl
                  label={t("appearance.density")}
                  value={appearance?.density ?? "comfortable"}
                  onValueChange={(value) =>
                    change({ appearance: { density: value as Density } })
                  }
                  options={[
                    {
                      value: "comfortable",
                      label: t("appearance.densityValues.comfortable"),
                    },
                    { value: "compact", label: t("appearance.densityValues.compact") },
                  ]}
                />
              </SettingRow>

              <Separator />

              <SettingRow
                title={t("appearance.fontSize")}
                description={t("appearance.fontSizeDescription")}
              >
                <SegmentedControl
                  label={t("appearance.fontSize")}
                  value={appearance?.font_size ?? "md"}
                  onValueChange={(value) =>
                    change({ appearance: { font_size: value as FontSizePreset } })
                  }
                  options={[
                    { value: "sm", label: t("appearance.fontSizeValues.sm") },
                    { value: "md", label: t("appearance.fontSizeValues.md") },
                    { value: "lg", label: t("appearance.fontSizeValues.lg") },
                  ]}
                />
              </SettingRow>

              <Separator />

              <SettingRow title={t("appearance.motion")} description={t("appearance.motionDescription")}>
                <SegmentedControl
                  label={t("appearance.motion")}
                  value={appearance?.motion ?? "full"}
                  onValueChange={(value) =>
                    change({ appearance: { motion: value as MotionPreference } })
                  }
                  options={[
                    { value: "full", label: t("appearance.motionValues.full") },
                    { value: "reduced", label: t("appearance.motionValues.reduced") },
                  ]}
                />
              </SettingRow>
            </SettingsSection>

            <SettingsSection id="language" icon={Languages} title={t("sections.language")}>
              <SettingRow title={t("language.title")} description={t("language.description")}>
                <SegmentedControl
                  label={t("language.title")}
                  value={language}
                  onValueChange={(value) => change({ language: value as LanguageCode })}
                  options={[
                    { value: "en", label: tCommon("language.english") },
                    { value: "my", label: tCommon("language.burmese") },
                    { value: "system", label: t("language.system") },
                  ]}
                />
              </SettingRow>
              <div className="flex gap-2 rounded-lg border border-border/60 bg-background/50 p-3 text-2xs leading-relaxed text-muted-foreground">
                <Info className="mt-0.5 size-icon-sm shrink-0 text-primary" aria-hidden="true" />
                <p>{t("language.burmeseNote")}</p>
              </div>
            </SettingsSection>

            <SettingsSection id="editor" icon={Type} title={t("sections.editor")}>
              <SettingRow title={t("editor.font")} description={t("editor.description")}>
                <SegmentedControl
                  label={t("editor.font")}
                  value={documentFont}
                  onValueChange={(value) =>
                    change({ editor: { document_font: value as DocumentFont } })
                  }
                  options={[
                    { value: "serif", label: t("editor.serif") },
                    { value: "sans", label: t("editor.sans") },
                  ]}
                />
              </SettingRow>
              <div
                className="rounded-lg border border-border/70 bg-card/80 px-4 py-3 text-sm leading-relaxed text-card-foreground shadow-xs"
                style={{
                  fontFamily:
                    documentFont === "sans"
                      ? "var(--font-document-sans)"
                      : "var(--font-document)",
                }}
              >
                {t("editor.preview")}
              </div>
            </SettingsSection>

            <SettingsSection id="ocr" icon={ScanText} title={t("sections.ocr")}>
              <div className="space-y-1">
                <h3 className="text-sm font-semibold">{t("ocr.title")}</h3>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  {t("ocr.description")}
                </p>
              </div>

              <div className="flex flex-col gap-3 rounded-lg border border-border/60 bg-background/40 p-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-medium">{t("ocr.status")}</span>
                  <Badge
                    variant={
                      ocrQuery.isLoading
                        ? "outline"
                        : ocr?.available
                          ? "success"
                          : "warning"
                    }
                  >
                    {ocrQuery.isLoading
                      ? t("ocr.checking")
                      : ocr?.available
                        ? t("ocr.ready")
                        : t("ocr.unavailable")}
                  </Badge>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5 self-start sm:self-auto"
                  disabled={ocrQuery.isFetching}
                  onClick={() =>
                    void ocrQuery.refetch()
                  }
                >
                  <RefreshCw className={ocrQuery.isFetching ? "animate-spin" : undefined} />
                  {t("ocr.refresh")}
                </Button>
              </div>

              {ocr?.available ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-lg border border-border/60 bg-background/40 p-3">
                    <p className="text-2xs uppercase tracking-wider text-muted-foreground">
                      {t("ocr.version")}
                    </p>
                    <p className="mt-1 font-mono text-sm font-semibold">
                      {ocr.version ?? "—"}
                    </p>
                  </div>
                  <div className="rounded-lg border border-border/60 bg-background/40 p-3">
                    <p className="text-2xs uppercase tracking-wider text-muted-foreground">
                      {t("ocr.languages")}
                    </p>
                    <p className="mt-1 break-words font-mono text-sm font-semibold">
                      {ocr.languages.length > 0 ? ocr.languages.join(", ") : t("ocr.noLanguages")}
                    </p>
                  </div>
                  <div className="rounded-lg border border-border/60 bg-background/40 p-3 sm:col-span-2">
                    <p className="text-2xs uppercase tracking-wider text-muted-foreground">
                      {t("ocr.command")}
                    </p>
                    <code className="mt-1 block break-all font-mono text-2xs text-foreground/90">
                      {ocr.command || t("ocr.notConfigured")}
                    </code>
                  </div>
                  {ocr.tessdata_dir ? (
                    <div className="rounded-lg border border-border/60 bg-background/40 p-3 sm:col-span-2">
                      <p className="text-2xs uppercase tracking-wider text-muted-foreground">
                        {t("ocr.tessdata")}
                      </p>
                      <code className="mt-1 block break-all font-mono text-2xs text-foreground/90">
                        {ocr.tessdata_dir}
                      </code>
                    </div>
                  ) : null}
                </div>
              ) : ocrQuery.isError ? (
                <div className="flex gap-2 rounded-lg border border-border/60 bg-background/50 p-3 text-2xs leading-relaxed text-muted-foreground">
                  <Info className="mt-0.5 size-icon-sm shrink-0 text-primary" aria-hidden="true" />
                  <p>{errorMessage(ocrQuery.error)}</p>
                </div>
              ) : (
                <div className="rounded-lg border border-border/60 bg-background/50 p-3 text-xs leading-relaxed text-muted-foreground">
                  {t(`ocr.unavailableReasons.${ocrReason}`)}
                </div>
              )}

              {ocr?.available && !ocr.languages.includes("mya") ? (
                <div className="flex gap-2 rounded-lg border border-warning/40 bg-warning/10 p-3 text-2xs leading-relaxed text-muted-foreground">
                  <Info className="mt-0.5 size-icon-sm shrink-0 text-warning" aria-hidden="true" />
                  <p>{t("ocr.missingBurmese")}</p>
                </div>
              ) : null}

              {!ocr?.available ? (
                <div className="space-y-2 rounded-lg border border-border/60 bg-background/50 p-3">
                  <h3 className="text-xs font-semibold">{t("ocr.setupTitle")}</h3>
                  <p className="text-2xs leading-relaxed text-muted-foreground">
                    {t("ocr.setupDescription")}
                  </p>
                  <Button asChild variant="ghost" size="sm" className="gap-1.5 px-0">
                    <a
                      href="https://tesseract-ocr.github.io/tessdoc/Installation.html"
                      target="_blank"
                      rel="noreferrer"
                    >
                      <ExternalLink />
                      {t("ocr.setupLink")}
                    </a>
                  </Button>
                </div>
              ) : null}

              <div className="flex gap-2 rounded-lg border border-border/60 bg-background/50 p-3 text-2xs leading-relaxed text-muted-foreground">
                <ShieldCheck className="mt-0.5 size-icon-sm shrink-0 text-success" aria-hidden="true" />
                <p>{t("ocr.privacy")}</p>
              </div>
            </SettingsSection>

            <SettingsSection id="ai" icon={Brain} title={t("sections.ai")}>
              <div className="space-y-1">
                <h3 className="text-sm font-semibold">{t("ai.title")}</h3>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  {t("ai.description")}
                </p>
              </div>

              <SettingRow title={t("ai.provider")} description={t("ai.providerDescription")}>
                <SegmentedControl
                  label={t("ai.provider")}
                  value={aiDraft.provider}
                  onValueChange={(value) => {
                    setProbeResult(null);
                    updateAiDraft({ provider: value as AiProviderKind });
                  }}
                  options={[
                    { value: "ollama", label: t("ai.providerOllama") },
                    { value: "openai_compatible", label: t("ai.providerOpenAI") },
                  ]}
                />
              </SettingRow>

              <SettingRow title={t("ai.baseUrl")} description={t("ai.baseUrlDescription")}>
                <Input
                  value={aiDraft.base_url}
                  placeholder={providerDefault}
                  spellCheck={false}
                  aria-label={t("ai.baseUrl")}
                  onChange={(event) => {
                    setProbeResult(null);
                    updateAiDraft({ base_url: event.target.value });
                  }}
                />
              </SettingRow>

              <SettingRow title={t("ai.model")} description={t("ai.modelDescription")}>
                <Input
                  value={aiDraft.model}
                  placeholder={t("ai.modelPlaceholder")}
                  spellCheck={false}
                  aria-label={t("ai.model")}
                  list={discoveredModels.length > 0 ? "ai-model-options" : undefined}
                  onChange={(event) => updateAiDraft({ model: event.target.value })}
                />
                {discoveredModels.length > 0 ? (
                  <datalist id="ai-model-options">
                    {discoveredModels.map((model) => (
                      <option key={model.id} value={model.id} />
                    ))}
                  </datalist>
                ) : null}
              </SettingRow>

              <div className="flex flex-col gap-2 rounded-lg border border-border/60 bg-background/40 p-3">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-medium">{t("ai.status")}</span>
                    <Badge
                      variant={
                        probeAi.isPending
                          ? "outline"
                          : probeResult?.status === "ready"
                            ? "success"
                            : probeResult
                              ? "warning"
                              : "outline"
                      }
                    >
                      {probeAi.isPending
                        ? t("ai.testing")
                        : probeResult?.status === "ready"
                          ? t("ai.connected")
                          : probeResult
                            ? t("ai.disconnected")
                            : t("ai.notTested")}
                    </Badge>
                    {probeResult?.version ? (
                      <span className="text-2xs text-muted-foreground">
                        v{probeResult.version}
                      </span>
                    ) : null}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5 self-start sm:self-auto"
                    disabled={probeAi.isPending}
                    onClick={testAiConnection}
                  >
                    <RefreshCw className={probeAi.isPending ? "animate-spin" : undefined} />
                    {t("ai.testConnection")}
                  </Button>
                </div>

                {probeResult?.status === "ready" ? (
                  <p className="text-2xs text-muted-foreground">
                    {discoveredModels.length > 0
                      ? t("ai.modelsFound", { count: discoveredModels.length })
                      : t("ai.noModels")}
                  </p>
                ) : probeResult ? (
                  <p className="text-2xs text-warning">
                    {t(`ai.errorReasons.${probeResult.error_code ?? "ai_unreachable"}`)}
                  </p>
                ) : (
                  <p className="text-2xs text-muted-foreground">{t("ai.testHint")}</p>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  disabled={!aiDirty || updateSettings.isPending}
                  onClick={saveAiProfile}
                >
                  {t("ai.saveProfile")}
                </Button>
                <span className="text-2xs text-muted-foreground">
                  {aiDirty
                    ? t("ai.unsaved")
                    : aiDraft.model
                      ? t("ai.enabledHint")
                      : t("ai.notConfigured")}
                </span>
              </div>

              <div className="flex gap-2 rounded-lg border border-border/60 bg-background/50 p-3 text-2xs leading-relaxed text-muted-foreground">
                <ShieldCheck className="mt-0.5 size-icon-sm shrink-0 text-success" aria-hidden="true" />
                <p>{t("ai.privacy")}</p>
              </div>
            </SettingsSection>

            <SettingsSection id="storage" icon={HardDrive} title={t("sections.storage")}>
              <div className="space-y-1.5">
                <p className="text-sm font-medium leading-snug">{t("storage.path")}</p>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  {t("storage.pathDescription")}
                </p>
                {health ? (
                  <div className="flex flex-col gap-2 rounded-lg border border-border/60 bg-muted/40 p-2.5 sm:flex-row sm:items-center">
                    <code className="min-w-0 flex-1 break-all font-mono text-2xs leading-relaxed text-foreground/90">
                      {health.data_dir}
                    </code>
                    <Button
                      variant="outline"
                      size="sm"
                      className="shrink-0 gap-1.5 self-start sm:self-auto"
                      onClick={() => void copyPath()}
                    >
                      {copied ? <Check className="text-success" /> : <Copy />}
                      {copied ? t("storage.copied") : t("storage.copyPath")}
                    </Button>
                  </div>
                ) : (
                  <p className="rounded-lg border border-dashed border-border/70 px-3 py-2 text-xs text-muted-foreground">
                    {t("storage.offline")}
                  </p>
                )}
              </div>

              <Separator />

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border border-border/60 bg-background/40 p-3">
                  <p className="text-2xs uppercase tracking-wider text-muted-foreground">
                    {t("storage.projects")}
                  </p>
                  <p className="mt-1 font-mono text-lg font-semibold">
                    {health ? formatNumber(health.projects, locale) : "—"}
                  </p>
                </div>
                <div className="rounded-lg border border-border/60 bg-background/40 p-3">
                  <p className="text-2xs uppercase tracking-wider text-muted-foreground">
                    {t("storage.version")}
                  </p>
                  <p className="mt-1 font-mono text-lg font-semibold">
                    {metaQuery.data ? `v${metaQuery.data.version}` : "—"}
                  </p>
                </div>
              </div>

              <div className="flex gap-2 rounded-lg border border-border/60 bg-background/50 p-3 text-2xs leading-relaxed text-muted-foreground">
                <ShieldCheck className="mt-0.5 size-icon-sm shrink-0 text-success" aria-hidden="true" />
                <p>{t("storage.privacyNote")}</p>
              </div>
            </SettingsSection>

            <SettingsSection id="about" icon={Info} title={t("sections.about")}>
              <div className="space-y-1">
                <h3 className="text-sm font-semibold">{t("about.title")}</h3>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  {t("about.principles")}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
                <span className="text-muted-foreground">
                  {t("about.version")}:{" "}
                  <span className="font-mono text-foreground">
                    v{metaQuery.data?.version ?? "0.1.0"}
                  </span>
                </span>
                {metaQuery.data?.repository_url ? (
                  <a
                    href={metaQuery.data.repository_url}
                    target="_blank"
                    rel="noreferrer"
                    className="focus-ring inline-flex items-center gap-1.5 rounded-md text-primary underline-offset-4 hover:underline"
                  >
                    <ExternalLink className="size-icon-sm" aria-hidden="true" />
                    {t("about.repo")}
                  </a>
                ) : null}
              </div>

              <Separator />

              <div className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t("roadmap.title")}
                </h3>
                <ul className="space-y-1.5">
                  {ROADMAP.map((item) => (
                    <li
                      key={item.key}
                      className="flex items-center justify-between gap-3 rounded-md bg-background/40 px-2.5 py-1.5 text-xs"
                    >
                      <span className="min-w-0 truncate">{t(`roadmap.${item.key}`)}</span>
                      <Badge variant={STATUS_VARIANT[item.status]} className="shrink-0">
                        {t(`roadmap.${item.status}`)}
                      </Badge>
                    </li>
                  ))}
                </ul>
              </div>
            </SettingsSection>
          </div>
        </div>
      </div>
    </div>
  );
}
