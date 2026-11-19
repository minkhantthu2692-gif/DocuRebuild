import {
  Brain,
  CircleAlert,
  History,
  KeyRound,
  Plus,
  RefreshCw,
  ShieldCheck,
  Star,
  Trash2,
} from "lucide-react";
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";

import type {
  AiConnection,
  AiConnectionStatus,
  AiCostClass,
  AiKey,
  AiModel,
  AiProviderInfo,
  AiRotationStrategy,
  AiTaskCapability,
  AiTaskId,
  AiTaskRoute,
} from "@docurebuild/shared-types";

import { AiUsageHistoryDialog } from "@/components/settings/ai-usage-history-dialog";
import { SettingRow, SettingsSection } from "@/components/settings/settings-section";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import {
  useAddAiKey,
  useAddAiModel,
  useAiConnection,
  useAiConnections,
  useAiMigration,
  useAiModels,
  useAiOverview,
  useAiPreferences,
  useAiProviders,
  useAiRoutes,
  useAiUsage,
  useClearAiUsage,
  useCreateAiConnection,
  useDeleteAiConnection,
  useDeleteAiKey,
  useFavoriteAiModel,
  useTestAiConnection,
  useUpdateAiConnection,
  useUpdateAiKey,
  useUpdateAiPreferences,
  useUpdateAiRoute,
} from "@/hooks/use-ai";
import { formatDateTime, formatNumber, resolveLocale } from "@/lib/format";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const ROTATION_STRATEGIES: readonly AiRotationStrategy[] = [
  "priority",
  "failover",
  "round_robin",
  "least_recent",
  "least_usage",
];

const COST_CLASSES: readonly AiCostClass[] = ["local", "free", "paid"];

const TASK_ORDER: readonly AiTaskId[] = [
  "ocr_cleanup",
  "region_proposals",
  "equation_transcription",
  "table_structure",
];

const NONE = "__none__";

const STATUS_VARIANT: Record<
  AiConnectionStatus,
  "success" | "warning" | "destructive" | "outline"
> = {
  connected: "success",
  untested: "outline",
  configuration_required: "warning",
  auth_failed: "destructive",
  rate_limited: "warning",
  quota_exhausted: "warning",
  unavailable: "warning",
  error: "destructive",
  disabled: "outline",
};

function formatCurrency(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 4,
  }).format(value);
}

/** A vision route only offers models that are known to accept images. */
function modelFitsCapability(model: AiModel, capability: AiTaskCapability): boolean {
  if (capability === "vision") {
    const modalities = model.input_modalities;
    return modalities === null || modalities.includes("image");
  }
  const modalities = model.output_modalities;
  return modalities === null || modalities.includes("text");
}

function modelSupportsVision(model: AiModel): boolean | null {
  const modalities = model.input_modalities;
  if (modalities === null) return null;
  return modalities.includes("image");
}

function providerFor(
  providers: AiProviderInfo[],
  connection: AiConnection,
): AiProviderInfo | undefined {
  return providers.find((item) => item.id === connection.provider);
}

/* -------------------------------------------------------------------------- */
/*                                  Connections                               */
/* -------------------------------------------------------------------------- */

interface ConnectionEditorProps {
  connection: AiConnection;
  provider: AiProviderInfo | undefined;
  locale: string;
}

function ConnectionEditor({ connection, provider, locale }: ConnectionEditorProps) {
  const { t } = useTranslation("settings");
  const { t: tCommon } = useTranslation("common");
  const errorMessage = useApiErrorMessage();
  const detailQuery = useAiConnection(connection.id);
  const update = useUpdateAiConnection(connection.id);
  const remove = useDeleteAiConnection();
  const test = useTestAiConnection(connection.id);
  const addKey = useAddAiKey(connection.id);
  const updateKey = useUpdateAiKey(connection.id);
  const deleteKey = useDeleteAiKey(connection.id);
  const addModel = useAddAiModel(connection.id);
  const favorite = useFavoriteAiModel(connection.id);

  const [name, setName] = useState(connection.name);
  const [baseUrl, setBaseUrl] = useState(connection.base_url);
  const [allowRemote, setAllowRemote] = useState(connection.allow_remote);
  const [costClass, setCostClass] = useState<AiCostClass>(connection.cost_class);
  const [enabled, setEnabled] = useState(connection.enabled);
  const [rotation, setRotation] = useState<AiRotationStrategy>(connection.rotation_strategy);
  const [maxAttempts, setMaxAttempts] = useState(String(connection.max_attempts));
  const [requestLimit, setRequestLimit] = useState(String(connection.request_limit));
  const [monthlyBudget, setMonthlyBudget] = useState(
    connection.monthly_budget_usd === null ? "" : String(connection.monthly_budget_usd),
  );
  const [testResult, setTestResult] = useState<{
    status: AiConnectionStatus;
    models_found: number;
    error_code: string | null;
    retry_after_seconds: number | null;
    message: string | null;
  } | null>(null);

  const [keyOpen, setKeyOpen] = useState(false);
  const [keyLabel, setKeyLabel] = useState("");
  const [keySecret, setKeySecret] = useState("");
  const [keyPriority, setKeyPriority] = useState("100");
  const [keyLimit, setKeyLimit] = useState("0");

  const [modelQuery, setModelQuery] = useState("");
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [manualModelOpen, setManualModelOpen] = useState(false);
  const [manualModelId, setManualModelId] = useState("");
  const [manualModelName, setManualModelName] = useState("");

  const modelsQuery = useAiModels(connection.id, {
    ...(modelQuery.trim() ? { query: modelQuery.trim() } : {}),
    favoritesOnly,
  });
  const models = modelsQuery.data ?? [];
  const keys = detailQuery.data?.keys ?? [];

  const parsedAttempts = Number(maxAttempts);
  const attemptsValid = Number.isInteger(parsedAttempts) && parsedAttempts >= 1 && parsedAttempts <= 10;
  const parsedLimit = Number(requestLimit);
  const limitValid = Number.isInteger(parsedLimit) && parsedLimit >= 0 && parsedLimit <= 100_000;
  const parsedBudget = monthlyBudget.trim() === "" ? null : Number(monthlyBudget);
  const budgetValid =
    parsedBudget === null || (Number.isFinite(parsedBudget) && parsedBudget >= 0);
  const dirty =
    name !== connection.name ||
    baseUrl !== connection.base_url ||
    allowRemote !== connection.allow_remote ||
    costClass !== connection.cost_class ||
    enabled !== connection.enabled ||
    rotation !== connection.rotation_strategy ||
    maxAttempts !== String(connection.max_attempts) ||
    requestLimit !== String(connection.request_limit) ||
    monthlyBudget !==
      (connection.monthly_budget_usd === null ? "" : String(connection.monthly_budget_usd));

  const save = () => {
    if (!attemptsValid || !limitValid || !budgetValid) return;
    update.mutate(
      {
        name,
        base_url: baseUrl,
        allow_remote: allowRemote,
        cost_class: costClass,
        enabled,
        rotation_strategy: rotation,
        max_attempts: parsedAttempts,
        request_limit: parsedLimit,
        monthly_budget_usd: parsedBudget,
      },
      {
        onSuccess: () => toast.success(t("ai.connectionSaved")),
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  };

  const runTest = () => {
    setTestResult(null);
    test.mutate(
      {},
      {
        onSuccess: (result) => {
          setTestResult(result);
          if (result.status === "connected") {
            toast.success(t("ai.modelsFound", { count: result.models_found }));
          } else if (result.error_code) {
            toast.error(
              t(`ai.connectionErrors.${result.error_code}`, {
                defaultValue: result.message ?? result.error_code,
              }),
            );
          }
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  };

  const submitKey = () => {
    if (!keySecret.trim()) return;
    addKey.mutate(
      {
        label: keyLabel.trim(),
        api_key: keySecret.trim(),
        priority: Number.isInteger(Number(keyPriority)) ? Number(keyPriority) : 100,
        request_limit: Number.isInteger(Number(keyLimit)) ? Number(keyLimit) : 0,
      },
      {
        onSuccess: () => {
          toast.success(t("ai.keyAdded"));
          setKeyOpen(false);
          setKeyLabel("");
          setKeySecret("");
          setKeyPriority("100");
          setKeyLimit("0");
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  };

  const toggleKey = (key: AiKey) => {
    updateKey.mutate(
      { keyId: key.id, payload: { enabled: !key.enabled, auth_failed: false } },
      { onError: (error) => toast.error(errorMessage(error)) },
    );
  };

  const removeKey = (key: AiKey) => {
    if (!window.confirm(t("ai.removeKeyConfirm"))) return;
    deleteKey.mutate(key.id, {
      onSuccess: () => toast.success(t("ai.keyRemoved")),
      onError: (error) => toast.error(errorMessage(error)),
    });
  };

  const submitManualModel = () => {
    if (!manualModelId.trim()) return;
    addModel.mutate(
      {
        model_id: manualModelId.trim(),
        ...(manualModelName.trim() ? { display_name: manualModelName.trim() } : {}),
      },
      {
        onSuccess: () => {
          toast.success(t("ai.modelAdded"));
          setManualModelOpen(false);
          setManualModelId("");
          setManualModelName("");
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  };

  const deleteConnection = () => {
    if (!window.confirm(t("ai.deleteConnectionConfirm"))) return;
    remove.mutate(connection.id, {
      onSuccess: () => toast.success(t("ai.connectionDeleted")),
      onError: (error) => toast.error(errorMessage(error)),
    });
  };

  return (
    <div className="space-y-4 rounded-lg border border-border/60 bg-background/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={STATUS_VARIANT[connection.status]}>
            {t(`ai.status.${connection.status}`)}
          </Badge>
          <span className="text-2xs text-muted-foreground">
            {t("ai.connectionSummary", {
              models: formatNumber(connection.model_count, locale),
              keys: formatNumber(connection.key_count, locale),
            })}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            disabled={test.isPending}
            onClick={runTest}
          >
            <RefreshCw className={test.isPending ? "animate-spin" : undefined} />
            {test.isPending ? t("ai.testing") : t("ai.testConnection")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5 text-destructive hover:text-destructive"
            disabled={remove.isPending}
            onClick={deleteConnection}
          >
            <Trash2 />
            {t("ai.deleteConnection")}
          </Button>
        </div>
      </div>

      {testResult ? (
        <div
          className={cn(
            "flex items-start gap-2 rounded-md border p-2.5 text-2xs leading-relaxed",
            testResult.status === "connected"
              ? "border-success/40 bg-success/5"
              : "border-warning/40 bg-warning/5",
          )}
        >
          <CircleAlert
            className={cn(
              "mt-0.5 size-icon-sm shrink-0",
              testResult.status === "connected" ? "text-success" : "text-warning",
            )}
            aria-hidden="true"
          />
          <div className="space-y-0.5">
            <p>
              {testResult.status === "connected"
                ? t("ai.modelsFound", { count: testResult.models_found })
                : t(`ai.connectionErrors.${testResult.error_code ?? "ai_provider_unavailable"}`, {
                    defaultValue: testResult.message ?? t("ai.testFailed"),
                  })}
            </p>
            {testResult.retry_after_seconds ? (
              <p className="text-muted-foreground">
                {t("ai.retryAfter", {
                  seconds: formatNumber(testResult.retry_after_seconds, locale),
                })}
              </p>
            ) : null}
          </div>
        </div>
      ) : (
        <p className="text-2xs leading-relaxed text-muted-foreground">{t("ai.testHint")}</p>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1 text-xs">
          <span className="font-medium">{t("ai.name")}</span>
          <Input
            value={name}
            placeholder={t("ai.namePlaceholder")}
            aria-label={t("ai.name")}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label className="space-y-1 text-xs">
          <span className="font-medium">{t("ai.baseUrl")}</span>
          <Input
            value={baseUrl}
            placeholder={provider?.default_base_url || t("ai.baseUrlPlaceholder")}
            spellCheck={false}
            aria-label={t("ai.baseUrl")}
            onChange={(event) => setBaseUrl(event.target.value)}
          />
          <span className="block text-2xs leading-relaxed text-muted-foreground">
            {t("ai.baseUrlDescription")}
          </span>
        </label>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1 text-xs">
          <span className="font-medium">{t("ai.costClass")}</span>
          <SegmentedControl
            label={t("ai.costClass")}
            value={costClass}
            onValueChange={(value) => setCostClass(value as AiCostClass)}
            options={COST_CLASSES.map((value) => ({
              value,
              label: t(`ai.costClassValues.${value}`),
            }))}
          />
          <p className="text-2xs leading-relaxed text-muted-foreground">
            {t(`ai.costClassHints.${costClass}`)}
          </p>
        </div>
        <div className="space-y-1 text-xs">
          <span className="font-medium">{t("ai.rotation")}</span>
          <Select value={rotation} onValueChange={(value) => setRotation(value as AiRotationStrategy)}>
            <SelectTrigger aria-label={t("ai.rotation")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ROTATION_STRATEGIES.map((value) => (
                <SelectItem key={value} value={value}>
                  {t(`ai.rotationStrategies.${value}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-2xs leading-relaxed text-muted-foreground">
            {t("ai.rotationDescription")}
          </p>
        </div>
      </div>

      <label className="flex items-start gap-2 text-xs leading-relaxed">
        <input
          type="checkbox"
          className="mt-0.5 size-3.5 shrink-0 accent-primary"
          checked={allowRemote}
          onChange={(event) => setAllowRemote(event.target.checked)}
        />
        <span>
          <span className="font-medium">{t("ai.allowRemote")}</span>
          <span className="mt-0.5 block text-2xs text-muted-foreground">
            {t("ai.allowRemoteDescription")}
          </span>
        </span>
      </label>

      <label className="flex items-start gap-2 text-xs leading-relaxed">
        <input
          type="checkbox"
          className="mt-0.5 size-3.5 shrink-0 accent-primary"
          checked={enabled}
          onChange={(event) => setEnabled(event.target.checked)}
        />
        <span>
          <span className="font-medium">{t("ai.enabled")}</span>
          <span className="mt-0.5 block text-2xs text-muted-foreground">
            {t("ai.enabledDescription")}
          </span>
        </span>
      </label>

      <div className="grid gap-3 sm:grid-cols-3">
        <label className="space-y-1 text-xs">
          <span className="font-medium">{t("ai.maxAttempts")}</span>
          <Input
            type="number"
            min={1}
            max={10}
            step={1}
            value={maxAttempts}
            aria-invalid={!attemptsValid}
            aria-label={t("ai.maxAttempts")}
            onChange={(event) => setMaxAttempts(event.target.value)}
          />
          <span className="block text-2xs text-muted-foreground">{t("ai.maxAttemptsHint")}</span>
        </label>
        <label className="space-y-1 text-xs">
          <span className="font-medium">{t("ai.connectionLimit")}</span>
          <Input
            type="number"
            min={0}
            step={1}
            value={requestLimit}
            aria-invalid={!limitValid}
            aria-label={t("ai.connectionLimit")}
            onChange={(event) => setRequestLimit(event.target.value)}
          />
          <span className="block text-2xs text-muted-foreground">{t("ai.connectionLimitHint")}</span>
        </label>
        <label className="space-y-1 text-xs">
          <span className="font-medium">{t("ai.connectionBudget")}</span>
          <Input
            type="number"
            min={0}
            step="0.01"
            value={monthlyBudget}
            placeholder={t("ai.noBudget")}
            aria-invalid={!budgetValid}
            aria-label={t("ai.connectionBudget")}
            onChange={(event) => setMonthlyBudget(event.target.value)}
          />
          <span className="block text-2xs text-muted-foreground">{t("ai.connectionBudgetHint")}</span>
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          disabled={!dirty || !attemptsValid || !limitValid || !budgetValid || update.isPending}
          onClick={save}
        >
          {t("ai.saveConnection")}
        </Button>
        <span className="text-2xs text-muted-foreground">
          {dirty ? t("ai.unsaved") : t("ai.savedHint")}
        </span>
      </div>

      <Separator />

      {/* Keys ----------------------------------------------------------------- */}
      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="space-y-0.5">
            <h4 className="flex items-center gap-1.5 text-xs font-semibold">
              <KeyRound className="size-3.5 text-primary" aria-hidden="true" />
              {t("ai.keysTitle")}
            </h4>
            <p className="text-2xs leading-relaxed text-muted-foreground">
              {t("ai.keysDescription")}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => setKeyOpen((value) => !value)}
          >
            <Plus />
            {t("ai.addKey")}
          </Button>
        </div>

        {keyOpen ? (
          <div className="space-y-2 rounded-md border border-border/60 bg-background/60 p-2.5">
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="space-y-1 text-xs">
                <span className="font-medium">{t("ai.keyLabel")}</span>
                <Input
                  value={keyLabel}
                  placeholder={t("ai.keyLabelPlaceholder")}
                  aria-label={t("ai.keyLabel")}
                  onChange={(event) => setKeyLabel(event.target.value)}
                />
              </label>
              <label className="space-y-1 text-xs">
                <span className="font-medium">{t("ai.apiKey")}</span>
                <Input
                  type="password"
                  value={keySecret}
                  placeholder={t("ai.apiKeyPlaceholder")}
                  autoComplete="off"
                  spellCheck={false}
                  aria-label={t("ai.apiKey")}
                  onChange={(event) => setKeySecret(event.target.value)}
                />
              </label>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="space-y-1 text-xs">
                <span className="font-medium">{t("ai.keyPriority")}</span>
                <Input
                  type="number"
                  min={0}
                  step={1}
                  value={keyPriority}
                  aria-label={t("ai.keyPriority")}
                  onChange={(event) => setKeyPriority(event.target.value)}
                />
              </label>
              <label className="space-y-1 text-xs">
                <span className="font-medium">{t("ai.keyLimit")}</span>
                <Input
                  type="number"
                  min={0}
                  step={1}
                  value={keyLimit}
                  aria-label={t("ai.keyLimit")}
                  onChange={(event) => setKeyLimit(event.target.value)}
                />
              </label>
            </div>
            <p className="text-2xs leading-relaxed text-muted-foreground">{t("ai.apiKeyHint")}</p>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                disabled={!keySecret.trim() || addKey.isPending}
                onClick={submitKey}
              >
                {t("ai.saveKey")}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setKeyOpen(false)}>
                {tCommon("actions.cancel")}
              </Button>
            </div>
          </div>
        ) : null}

        {keys.length === 0 ? (
          <p className="text-2xs text-muted-foreground">
            {provider?.requires_api_key ? t("ai.keyRequired") : t("ai.noKeysNeeded")}
          </p>
        ) : (
          <ul className="divide-y divide-border/60 overflow-hidden rounded-md border border-border/60">
            {keys.map((key) => (
              <li key={key.id} className="flex flex-wrap items-center justify-between gap-2 px-2.5 py-2">
                <div className="min-w-0">
                  <p className="truncate text-xs font-medium">
                    {key.label || t("ai.keyUntitled")}
                  </p>
                  <p className="text-2xs text-muted-foreground">
                    {key.last_used_at
                      ? t("ai.keyLastUsed", {
                          time: formatDateTime(key.last_used_at, locale),
                        })
                      : t("ai.keyNeverUsed")}
                    {key.cooldown_until
                      ? ` · ${t("ai.keyCooldown", {
                          time: formatDateTime(key.cooldown_until, locale),
                        })}`
                      : ""}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge variant={key.enabled ? "success" : "outline"}>
                    {key.enabled ? t("ai.keyEnabled") : t("ai.keyDisabled")}
                  </Badge>
                  {key.auth_failed ? (
                    <Badge variant="destructive">{t("ai.keyAuthFailed")}</Badge>
                  ) : null}
                  <Button variant="ghost" size="sm" onClick={() => toggleKey(key)}>
                    {key.enabled ? t("ai.disableKey") : t("ai.enableKey")}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => removeKey(key)}
                  >
                    {tCommon("actions.remove")}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Separator />

      {/* Models --------------------------------------------------------------- */}
      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="space-y-0.5">
            <h4 className="text-xs font-semibold">{t("ai.modelsTitle")}</h4>
            <p className="text-2xs leading-relaxed text-muted-foreground">
              {t("ai.modelsDescription")}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {provider?.allows_manual_models ? (
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => setManualModelOpen((value) => !value)}
              >
                <Plus />
                {t("ai.manualModel")}
              </Button>
            ) : null}
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              disabled={test.isPending}
              onClick={runTest}
            >
              <RefreshCw className={test.isPending ? "animate-spin" : undefined} />
              {t("ai.refreshModels")}
            </Button>
          </div>
        </div>

        {manualModelOpen ? (
          <div className="space-y-2 rounded-md border border-border/60 bg-background/60 p-2.5">
            <p className="text-2xs leading-relaxed text-muted-foreground">
              {t("ai.manualModelDescription")}
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="space-y-1 text-xs">
                <span className="font-medium">{t("ai.modelId")}</span>
                <Input
                  value={manualModelId}
                  spellCheck={false}
                  aria-label={t("ai.modelId")}
                  onChange={(event) => setManualModelId(event.target.value)}
                />
              </label>
              <label className="space-y-1 text-xs">
                <span className="font-medium">{t("ai.modelDisplayName")}</span>
                <Input
                  value={manualModelName}
                  aria-label={t("ai.modelDisplayName")}
                  onChange={(event) => setManualModelName(event.target.value)}
                />
              </label>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                disabled={!manualModelId.trim() || addModel.isPending}
                onClick={submitManualModel}
              >
                {t("ai.addModel")}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setManualModelOpen(false)}>
                {tCommon("actions.cancel")}
              </Button>
            </div>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <Input
            value={modelQuery}
            placeholder={t("ai.searchModelsPlaceholder")}
            aria-label={t("ai.searchModels")}
            className="sm:max-w-64"
            onChange={(event) => setModelQuery(event.target.value)}
          />
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              className="size-3.5 accent-primary"
              checked={favoritesOnly}
              onChange={(event) => setFavoritesOnly(event.target.checked)}
            />
            {t("ai.favoritesOnly")}
          </label>
        </div>

        {modelsQuery.isLoading ? (
          <div className="flex items-center gap-2 py-2 text-2xs text-muted-foreground">
            <Spinner />
            {t("ai.modelsLoading")}
          </div>
        ) : models.length === 0 ? (
          <p className="text-2xs text-muted-foreground">
            {modelQuery || favoritesOnly ? t("ai.noModelMatches") : t("ai.noModels")}
          </p>
        ) : (
          <ul className="scrollbar-thin max-h-72 divide-y divide-border/60 overflow-y-auto rounded-md border border-border/60">
            {models.map((model) => {
              const vision = modelSupportsVision(model);
              return (
                <li
                  key={model.id}
                  className="flex flex-wrap items-center justify-between gap-2 px-2.5 py-2"
                >
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium">
                      {model.display_name || model.model_id}
                    </p>
                    <p className="truncate font-mono text-2xs text-muted-foreground">
                      {model.model_id}
                      {model.source === "manual" ? ` · ${t("ai.manualTag")}` : ""}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {vision === true ? <Badge variant="success">{t("ai.visionCapable")}</Badge> : null}
                    {vision === false ? <Badge variant="outline">{t("ai.textOnly")}</Badge> : null}
                    {vision === null ? (
                      <Badge variant="outline">{t("ai.modelUnverified")}</Badge>
                    ) : null}
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={model.favorite ? t("ai.unfavorite") : t("ai.favorite")}
                      aria-pressed={model.favorite}
                      onClick={() =>
                        favorite.mutate(
                          { model_id: model.model_id, favorite: !model.favorite },
                          { onError: (error) => toast.error(errorMessage(error)) },
                        )
                      }
                    >
                      <Star
                        className={model.favorite ? "fill-warning text-warning" : undefined}
                        aria-hidden="true"
                      />
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*                                    Routes                                  */
/* -------------------------------------------------------------------------- */

interface RouteRowProps {
  route: AiTaskRoute;
  connections: AiConnection[];
}

function RouteRow({ route, connections }: RouteRowProps) {
  const { t } = useTranslation("settings");
  const errorMessage = useApiErrorMessage();
  const update = useUpdateAiRoute();
  const isDefault = route.task === "default";

  const [connectionId, setConnectionId] = useState(route.connection_id ?? "");
  const [modelId, setModelId] = useState(route.model_id ?? "");
  const [fallbackConnectionId, setFallbackConnectionId] = useState(
    route.fallback_connection_id ?? "",
  );
  const [fallbackModelId, setFallbackModelId] = useState(route.fallback_model_id ?? "");
  const [temperature, setTemperature] = useState(String(route.temperature));
  const [timeout, setTimeout] = useState(String(route.timeout_seconds));
  const [requestLimit, setRequestLimit] = useState(String(route.request_limit));
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const modelsQuery = useAiModels(connectionId || null, { capability: route.capability });
  const fallbackModelsQuery = useAiModels(fallbackConnectionId || null, {
    capability: route.capability,
  });
  const models = modelsQuery.data ?? [];
  const fallbackModels = fallbackModelsQuery.data ?? [];

  const modelOptions = models.filter((model) => modelFitsCapability(model, route.capability));
  const fallbackOptions = fallbackModels.filter((model) =>
    modelFitsCapability(model, route.capability),
  );
  const hasModel = (list: AiModel[], value: string) =>
    list.some((model) => model.model_id === value);
  const parsedTemperature = Number(temperature);
  const temperatureValid =
    Number.isFinite(parsedTemperature) && parsedTemperature >= 0 && parsedTemperature <= 2;
  const parsedTimeout = Number(timeout);
  const timeoutValid = Number.isInteger(parsedTimeout) && parsedTimeout >= 5 && parsedTimeout <= 600;
  const parsedLimit = Number(requestLimit);
  const limitValid = Number.isInteger(parsedLimit) && parsedLimit >= 0 && parsedLimit <= 100_000;
  const dirty =
    connectionId !== (route.connection_id ?? "") ||
    modelId !== (route.model_id ?? "") ||
    fallbackConnectionId !== (route.fallback_connection_id ?? "") ||
    fallbackModelId !== (route.fallback_model_id ?? "") ||
    temperature !== String(route.temperature) ||
    timeout !== String(route.timeout_seconds) ||
    requestLimit !== String(route.request_limit);

  const taskLabel = isDefault ? t("ai.defaultRoute") : t(`ai.tasks.${route.task}`);
  const valid = temperatureValid && timeoutValid && limitValid;
  const missingModel = Boolean(connectionId) && !modelId;

  const save = () => {
    if (!valid || missingModel) return;
    update.mutate(
      {
        task: route.task,
        payload: {
          connection_id: connectionId || null,
          model_id: connectionId ? modelId : null,
          fallback_connection_id: fallbackConnectionId || null,
          fallback_model_id: fallbackConnectionId ? fallbackModelId : null,
          temperature: parsedTemperature,
          timeout_seconds: parsedTimeout,
          request_limit: parsedLimit,
        },
      },
      {
        onSuccess: () => toast.success(t("ai.routeSaved")),
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  };

  return (
    <div className="space-y-2 rounded-md border border-border/60 bg-background/40 p-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="text-xs font-semibold">{taskLabel}</h4>
          <Badge variant={route.configured ? "success" : "outline"}>
            {route.configured ? t("ai.routeConfigured") : t("ai.routeNotConfigured")}
          </Badge>
          <Badge variant="outline">
            {route.capability === "vision" ? t("ai.capabilityVision") : t("ai.capabilityText")}
          </Badge>
        </div>
        <Button variant="ghost" size="sm" onClick={() => setAdvancedOpen((value) => !value)}>
          {advancedOpen ? t("ai.hideAdvanced") : t("ai.showAdvanced")}
        </Button>
      </div>

      {isDefault ? (
        <p className="text-2xs leading-relaxed text-muted-foreground">
          {t("ai.defaultRouteDescription")}
        </p>
      ) : null}

      <div className="grid gap-2 sm:grid-cols-2">
        <label className="space-y-1 text-xs">
          <span className="font-medium">{t("ai.routeConnection")}</span>
          <Select
            value={connectionId || NONE}
            onValueChange={(value) => {
              const next = value === NONE ? "" : value;
              setConnectionId(next);
              setModelId("");
            }}
          >
            <SelectTrigger aria-label={`${taskLabel}: ${t("ai.routeConnection")}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>
                {isDefault ? t("ai.routeNone") : t("ai.routeInherit")}
              </SelectItem>
              {connections.map((connection) => (
                <SelectItem key={connection.id} value={connection.id}>
                  {connection.name} · {connection.provider_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>

        <label className="space-y-1 text-xs">
          <span className="font-medium">{t("ai.routeModel")}</span>
          <Select
            value={modelId || NONE}
            disabled={!connectionId}
            onValueChange={(value) => setModelId(value === NONE ? "" : value)}
          >
            <SelectTrigger aria-label={`${taskLabel}: ${t("ai.routeModel")}`}>
              <SelectValue placeholder={t("ai.routeChooseModel")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>{t("ai.routeChooseModel")}</SelectItem>
              {modelId && !hasModel(modelOptions, modelId) ? (
                <SelectItem value={modelId}>{modelId}</SelectItem>
              ) : null}
              {modelOptions.map((model) => (
                <SelectItem key={model.id} value={model.model_id}>
                  {model.display_name || model.model_id}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <label className="space-y-1 text-xs">
          <span className="font-medium">{t("ai.routeFallbackConnection")}</span>
          <Select
            value={fallbackConnectionId || NONE}
            onValueChange={(value) => {
              setFallbackConnectionId(value === NONE ? "" : value);
              setFallbackModelId("");
            }}
          >
            <SelectTrigger aria-label={`${taskLabel}: ${t("ai.routeFallbackConnection")}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>{t("ai.routeNoFallback")}</SelectItem>
              {connections
                .filter((connection) => connection.id !== connectionId)
                .map((connection) => (
                  <SelectItem key={connection.id} value={connection.id}>
                    {connection.name} · {connection.provider_name}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        </label>

        <label className="space-y-1 text-xs">
          <span className="font-medium">{t("ai.routeFallbackModel")}</span>
          <Select
            value={fallbackModelId || NONE}
            disabled={!fallbackConnectionId}
            onValueChange={(value) => setFallbackModelId(value === NONE ? "" : value)}
          >
            <SelectTrigger aria-label={`${taskLabel}: ${t("ai.routeFallbackModel")}`}>
              <SelectValue placeholder={t("ai.routeChooseModel")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>{t("ai.routeChooseModel")}</SelectItem>
              {fallbackModelId && !hasModel(fallbackOptions, fallbackModelId) ? (
                <SelectItem value={fallbackModelId}>{fallbackModelId}</SelectItem>
              ) : null}
              {fallbackOptions.map((model) => (
                <SelectItem key={model.id} value={model.model_id}>
                  {model.display_name || model.model_id}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
      </div>

      {advancedOpen ? (
        <div className="grid gap-2 sm:grid-cols-3">
          <label className="space-y-1 text-xs">
            <span className="font-medium">{t("ai.routeTemperature")}</span>
            <Input
              type="number"
              min={0}
              max={2}
              step="0.1"
              value={temperature}
              aria-invalid={!temperatureValid}
              aria-label={`${taskLabel}: ${t("ai.routeTemperature")}`}
              onChange={(event) => setTemperature(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="font-medium">{t("ai.routeTimeout")}</span>
            <Input
              type="number"
              min={5}
              max={600}
              step={1}
              value={timeout}
              aria-invalid={!timeoutValid}
              aria-label={`${taskLabel}: ${t("ai.routeTimeout")}`}
              onChange={(event) => setTimeout(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="font-medium">{t("ai.routeLimit")}</span>
            <Input
              type="number"
              min={0}
              step={1}
              value={requestLimit}
              aria-invalid={!limitValid}
              aria-label={`${taskLabel}: ${t("ai.routeLimit")}`}
              onChange={(event) => setRequestLimit(event.target.value)}
            />
          </label>
        </div>
      ) : null}

      {route.warnings.length > 0 ? (
        <ul className="space-y-0.5">
          {route.warnings.map((warning) => (
            <li key={warning} className="flex items-start gap-1.5 text-2xs text-warning">
              <CircleAlert className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
              {t(`ai.routeWarnings.${warning}`, { defaultValue: warning })}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={!dirty || !valid || missingModel || update.isPending} onClick={save}>
          {t("ai.saveRoute")}
        </Button>
        {missingModel ? (
          <span className="text-2xs text-warning">{t("ai.routeModelRequired")}</span>
        ) : dirty ? (
          <span className="text-2xs text-muted-foreground">{t("ai.unsaved")}</span>
        ) : null}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*                                Add connection                              */
/* -------------------------------------------------------------------------- */

interface AddConnectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  providers: AiProviderInfo[];
  onCreated: (connectionId: string) => void;
}

function AddConnectionDialog({ open, onOpenChange, providers, onCreated }: AddConnectionDialogProps) {
  const { t } = useTranslation("settings");
  const { t: tCommon } = useTranslation("common");
  const errorMessage = useApiErrorMessage();
  const queryClient = useQueryClient();
  const create = useCreateAiConnection();
  const titleId = useId();

  const [providerId, setProviderId] = useState(providers[0]?.id ?? "ollama");
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [allowRemote, setAllowRemote] = useState(false);
  const [costClass, setCostClass] = useState<AiCostClass>("local");
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);

  const provider = providers.find((item) => item.id === providerId);
  const isLocal = provider?.local_default === true;
  const requiresBaseUrl = provider?.requires_base_url === true;

  useEffect(() => {
    if (!open) return;
    const first = providers[0];
    setProviderId(first?.id ?? "ollama");
    setName("");
    setBaseUrl("");
    setAllowRemote(false);
    setCostClass(first?.local_default ? "local" : "paid");
    setApiKey("");
    setSaving(false);
    // Reset only when the dialog opens; provider data is stable once loaded.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const changeProvider = (value: string) => {
    setProviderId(value);
    setBaseUrl("");
    setAllowRemote(false);
    setCostClass(providers.find((item) => item.id === value)?.local_default ? "local" : "paid");
  };

  const canSubmit =
    Boolean(provider) &&
    (!requiresBaseUrl || baseUrl.trim().length > 0) &&
    (!provider?.requires_api_key || apiKey.trim().length > 0) &&
    (isLocal || allowRemote) &&
    !saving;

  const submit = async () => {
    if (!provider || !canSubmit) return;
    setSaving(true);
    try {
      const created = await create.mutateAsync({
        provider: provider.id,
        ...(name.trim() ? { name: name.trim() } : {}),
        base_url: baseUrl.trim(),
        allow_remote: allowRemote,
        cost_class: costClass,
      });
      if (apiKey.trim()) {
        await api.addAiKey(created.id, {
          api_key: apiKey.trim(),
          label: provider.name,
        });
        void queryClient.invalidateQueries({ queryKey: ["ai"] });
      }
      toast.success(t("ai.connectionCreated"));
      onCreated(created.id);
      onOpenChange(false);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  return (
    <div className="space-y-3 rounded-lg border border-primary/30 bg-primary/5 p-3">
      <h3 id={titleId} className="text-sm font-semibold">
        {t("ai.addConnectionTitle")}
      </h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1 text-xs">
          <span className="font-medium">{t("ai.provider")}</span>
          <Select value={providerId} onValueChange={changeProvider}>
            <SelectTrigger aria-label={t("ai.provider")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {providers.map((item) => (
                <SelectItem key={item.id} value={item.id}>
                  {item.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="block text-2xs text-muted-foreground">
            {provider?.local_default ? t("ai.providerLocalHint") : t("ai.providerRemoteHint")}
          </span>
        </label>
        <label className="space-y-1 text-xs">
          <span className="font-medium">{t("ai.name")}</span>
          <Input
            value={name}
            placeholder={provider?.name ?? t("ai.namePlaceholder")}
            aria-label={t("ai.name")}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
      </div>

      <label className="space-y-1 text-xs">
        <span className="font-medium">{t("ai.baseUrl")}</span>
        <Input
          value={baseUrl}
          placeholder={provider?.default_base_url || t("ai.baseUrlPlaceholder")}
          spellCheck={false}
          aria-label={t("ai.baseUrl")}
          onChange={(event) => setBaseUrl(event.target.value)}
        />
        <span className="block text-2xs leading-relaxed text-muted-foreground">
          {t("ai.baseUrlDescription")}
        </span>
      </label>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1 text-xs">
          <span className="font-medium">{t("ai.costClass")}</span>
          <SegmentedControl
            label={t("ai.costClass")}
            value={costClass}
            onValueChange={(value) => setCostClass(value as AiCostClass)}
            options={COST_CLASSES.map((value) => ({
              value,
              label: t(`ai.costClassValues.${value}`),
            }))}
          />
          <p className="text-2xs leading-relaxed text-muted-foreground">
            {t(`ai.costClassHints.${costClass}`)}
          </p>
        </div>
        <label className="space-y-1 text-xs">
          <span className="font-medium">
            {provider?.requires_api_key ? t("ai.apiKey") : t("ai.apiKeyOptional")}
          </span>
          <Input
            type="password"
            value={apiKey}
            placeholder={t("ai.apiKeyPlaceholder")}
            autoComplete="off"
            spellCheck={false}
            aria-label={t("ai.apiKey")}
            onChange={(event) => setApiKey(event.target.value)}
          />
          <span className="block text-2xs leading-relaxed text-muted-foreground">
            {t("ai.apiKeyHint")}
          </span>
        </label>
      </div>

      {!isLocal ? (
        <label className="flex items-start gap-2 text-xs leading-relaxed">
          <input
            type="checkbox"
            className="mt-0.5 size-3.5 shrink-0 accent-primary"
            checked={allowRemote}
            onChange={(event) => setAllowRemote(event.target.checked)}
          />
          <span>
            <span className="font-medium">{t("ai.allowRemote")}</span>
            <span className="mt-0.5 block text-2xs text-muted-foreground">
              {t("ai.allowRemoteDescription")}
            </span>
          </span>
        </label>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={!canSubmit} onClick={() => void submit()}>
          {saving ? t("ai.saving") : t("ai.addConnection")}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
          {tCommon("actions.cancel")}
        </Button>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*                                   Settings                                 */
/* -------------------------------------------------------------------------- */

export function AiSettings() {
  const { t, i18n } = useTranslation("settings");
  const { t: tCommon } = useTranslation("common");
  const locale = resolveLocale(i18n.resolvedLanguage);
  const errorMessage = useApiErrorMessage();

  const providersQuery = useAiProviders();
  const connectionsQuery = useAiConnections();
  const overviewQuery = useAiOverview();
  const preferencesQuery = useAiPreferences();
  const usageQuery = useAiUsage();
  const routesQuery = useAiRoutes();
  const migrationQuery = useAiMigration();
  const updatePreferences = useUpdateAiPreferences();
  const clearUsage = useClearAiUsage();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [dailyLimit, setDailyLimit] = useState<string | null>(null);
  const [monthlyBudget, setMonthlyBudget] = useState<string | null>(null);

  const providers = providersQuery.data?.providers ?? [];
  const connections = connectionsQuery.data?.connections ?? [];
  const routes = routesQuery.data?.routes ?? [];
  const usage = usageQuery.data;
  const overview = overviewQuery.data;
  const preferences = preferencesQuery.data;

  const selected =
    connections.find((connection) => connection.id === selectedId) ?? connections[0] ?? null;

  const dailyValue = dailyLimit ?? String(preferences?.daily_request_limit ?? 0);
  const budgetValue =
    monthlyBudget ??
    (preferences?.monthly_budget_usd === null || preferences?.monthly_budget_usd === undefined
      ? ""
      : String(preferences.monthly_budget_usd));
  const parsedDaily = Number(dailyValue);
  const dailyValid =
    dailyValue.trim() !== "" &&
    Number.isInteger(parsedDaily) &&
    parsedDaily >= 0 &&
    parsedDaily <= 100_000;
  const parsedBudget = budgetValue.trim() === "" ? null : Number(budgetValue);
  const budgetValid =
    parsedBudget === null || (Number.isFinite(parsedBudget) && parsedBudget >= 0);
  const preferencesDirty =
    preferences !== undefined &&
    (parsedDaily !== preferences.daily_request_limit ||
      parsedBudget !== preferences.monthly_budget_usd);

  const savePreferences = () => {
    if (!dailyValid || !budgetValid) return;
    updatePreferences.mutate(
      { daily_request_limit: parsedDaily, monthly_budget_usd: parsedBudget },
      {
        onSuccess: () => {
          setDailyLimit(null);
          setMonthlyBudget(null);
          toast.success(t("ai.preferencesSaved"));
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  };

  const clearLedger = () => {
    if (!window.confirm(t("ai.clearUsageConfirm"))) return;
    clearUsage.mutate(undefined, {
      onSuccess: () => toast.success(t("ai.usageCleared")),
      onError: (error) => toast.error(errorMessage(error)),
    });
  };

  return (
    <SettingsSection id="ai" icon={Brain} title={t("sections.ai")}>
      <div className="space-y-1">
        <h3 className="text-sm font-semibold">{t("ai.title")}</h3>
        <p className="text-xs leading-relaxed text-muted-foreground">{t("ai.description")}</p>
      </div>

      {overview ? (
        <div className="flex flex-wrap items-center gap-2 text-2xs text-muted-foreground">
          <Badge variant="outline">
            {t("ai.overviewConnections", {
              value: formatNumber(overview.connection_count, locale),
            })}
          </Badge>
          <Badge variant="outline">
            {t("ai.overviewModels", { value: formatNumber(overview.model_count, locale) })}
          </Badge>
          <Badge
            variant={
              overview.configured_task_count === overview.task_count ? "success" : "warning"
            }
          >
            {t("ai.overviewTasks", {
              configured: formatNumber(overview.configured_task_count, locale),
              total: formatNumber(overview.task_count, locale),
            })}
          </Badge>
        </div>
      ) : null}

      {migrationQuery.data?.needed ? (
        <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/5 p-3 text-2xs leading-relaxed">
          <CircleAlert className="mt-0.5 size-icon-sm shrink-0 text-warning" aria-hidden="true" />
          <div>
            <p className="font-medium">{t("ai.migrationTitle")}</p>
            <p className="text-muted-foreground">{t("ai.migrationDescription")}</p>
          </div>
        </div>
      ) : null}

      {/* Connections ---------------------------------------------------------- */}
      <div className="space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="space-y-0.5">
            <h4 className="text-xs font-semibold">{t("ai.connectionsTitle")}</h4>
            <p className="max-w-xl text-2xs leading-relaxed text-muted-foreground">
              {t("ai.connectionsDescription")}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            disabled={providers.length === 0}
            onClick={() => setAddOpen((value) => !value)}
          >
            <Plus />
            {t("ai.addConnection")}
          </Button>
        </div>

        <AddConnectionDialog
          open={addOpen}
          onOpenChange={setAddOpen}
          providers={providers}
          onCreated={(connectionId) => setSelectedId(connectionId)}
        />

        {connectionsQuery.isLoading ? (
          <div className="flex items-center gap-2 py-2 text-2xs text-muted-foreground">
            <Spinner />
            {t("ai.connectionsLoading")}
          </div>
        ) : connections.length === 0 ? (
          <EmptyState
            icon={KeyRound}
            title={t("ai.noConnections")}
            description={t("ai.noConnectionsDescription")}
          />
        ) : (
          <ul className="space-y-1.5">
            {connections.map((connection) => {
              const active = selected?.id === connection.id;
              return (
                <li key={connection.id}>
                  <button
                    type="button"
                    aria-pressed={active}
                    onClick={() => setSelectedId(connection.id)}
                    className={cn(
                      "focus-ring flex w-full flex-wrap items-center justify-between gap-2 rounded-md border px-2.5 py-2 text-left transition-colors",
                      active
                        ? "border-primary bg-primary/5"
                        : "border-border/60 bg-background/40 hover:border-primary/40 hover:bg-accent/40",
                    )}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-xs font-medium">
                        {connection.name}
                      </span>
                      <span className="block truncate text-2xs text-muted-foreground">
                        {connection.provider_name} ·{" "}
                        {t(`ai.costClassValues.${connection.cost_class}`)} ·{" "}
                        {t("ai.connectionSummary", {
                          models: formatNumber(connection.model_count, locale),
                          keys: formatNumber(connection.key_count, locale),
                        })}
                      </span>
                    </span>
                    <Badge variant={STATUS_VARIANT[connection.status]}>
                      {t(`ai.status.${connection.status}`)}
                    </Badge>
                  </button>
                </li>
              );
            })}
          </ul>
        )}

        {selected ? (
          <ConnectionEditor
            key={`${selected.id}:${selected.updated_at ?? ""}`}
            connection={selected}
            provider={providerFor(providers, selected)}
            locale={locale}
          />
        ) : null}
      </div>

      <Separator />

      {/* Routes --------------------------------------------------------------- */}
      <div className="space-y-2">
        <div className="space-y-0.5">
          <h4 className="text-xs font-semibold">{t("ai.routesTitle")}</h4>
          <p className="max-w-xl text-2xs leading-relaxed text-muted-foreground">
            {t("ai.routesDescription")}
          </p>
        </div>

        {routesQuery.isLoading ? (
          <div className="flex items-center gap-2 py-2 text-2xs text-muted-foreground">
            <Spinner />
            {t("ai.routesLoading")}
          </div>
        ) : connections.length === 0 ? (
          <p className="text-2xs text-muted-foreground">{t("ai.routesNeedConnection")}</p>
        ) : (
          <div className="space-y-2">
            {[...routes]
              .sort((a, b) => {
                const rank = (task: string) =>
                  task === "default" ? -1 : TASK_ORDER.indexOf(task as AiTaskId);
                return rank(a.task) - rank(b.task);
              })
              .map((route) => (
                <RouteRow
                  key={`${route.task}:${route.updated_at ?? ""}:${route.connection_id ?? ""}:${route.model_id ?? ""}`}
                  route={route}
                  connections={connections}
                />
              ))}
          </div>
        )}
      </div>

      <Separator />

      {/* Preferences and usage ------------------------------------------------ */}
      <div className="space-y-3">
        <div className="space-y-0.5">
          <h4 className="text-xs font-semibold">{t("ai.usageTitle")}</h4>
          <p className="max-w-xl text-2xs leading-relaxed text-muted-foreground">
            {t("ai.usageDescription")}
          </p>
        </div>

        <SettingRow title={t("ai.dailyLimit")} description={t("ai.dailyLimitDescription")}>
          <div className="space-y-1.5">
            <Input
              type="number"
              min={0}
              max={100_000}
              step={1}
              value={dailyValue}
              aria-invalid={!dailyValid}
              aria-label={t("ai.dailyLimit")}
              onChange={(event) => setDailyLimit(event.target.value)}
            />
            <p className="text-2xs leading-relaxed text-muted-foreground">
              {usage
                ? usage.request_limit > 0
                  ? t("ai.usageLimited", {
                      used: formatNumber(usage.used, locale),
                      limit: formatNumber(usage.request_limit, locale),
                    })
                  : t("ai.usageUnlimited", { used: formatNumber(usage.used, locale) })
                : t("ai.usageLoading")}
            </p>
          </div>
        </SettingRow>

        <SettingRow title={t("ai.monthlyBudget")} description={t("ai.monthlyBudgetDescription")}>
          <div className="space-y-1.5">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={budgetValue}
              placeholder={t("ai.noBudget")}
              aria-invalid={!budgetValid}
              aria-label={t("ai.monthlyBudget")}
              onChange={(event) => setMonthlyBudget(event.target.value)}
            />
            <p className="text-2xs leading-relaxed text-muted-foreground">
              {usage
                ? t("ai.monthlyCost", {
                    cost: formatCurrency(usage.monthly_cost_usd, locale),
                  })
                : t("ai.usageLoading")}
            </p>
          </div>
        </SettingRow>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            disabled={
              !preferencesDirty || !dailyValid || !budgetValid || updatePreferences.isPending
            }
            onClick={savePreferences}
          >
            {t("ai.savePreferences")}
          </Button>
          {!dailyValid ? (
            <span className="text-2xs text-warning">{t("ai.limitInvalid")}</span>
          ) : null}
        </div>

        {usage ? (
          <div className="space-y-2 rounded-lg border border-border/60 bg-background/40 p-3">
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-2xs text-muted-foreground">
              <span>
                {t("ai.usageRequests", { used: formatNumber(usage.used, locale) })}
              </span>
              <span>{t("ai.usageTokens", { value: formatNumber(usage.total_tokens, locale) })}</span>
              <span>{t("ai.usageCost", { cost: formatCurrency(usage.estimated_cost_usd, locale) })}</span>
              {usage.unpriced_requests > 0 ? (
                <span className="text-warning">
                  {t("ai.usageUnpriced", {
                    value: formatNumber(usage.unpriced_requests, locale),
                  })}
                </span>
              ) : null}
            </div>

            {usage.by_task.length > 0 ? (
              <div className="space-y-1">
                <p className="text-2xs font-medium text-muted-foreground">{t("ai.usageByTask")}</p>
                <ul className="flex flex-wrap gap-x-3 gap-y-1 text-2xs text-muted-foreground">
                  {usage.by_task.map((row) => (
                    <li key={row.task}>
                      {t("ai.usageTaskCount", {
                        task: t(`ai.tasks.${row.task}`, {
                          defaultValue: t("ai.history.unknownTask"),
                        }),
                        requests: formatNumber(row.used, locale),
                      })}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {usage.by_connection.length > 0 ? (
              <div className="space-y-1">
                <p className="text-2xs font-medium text-muted-foreground">
                  {t("ai.usageByConnection")}
                </p>
                <ul className="space-y-0.5 text-2xs text-muted-foreground">
                  {usage.by_connection.map((row) => (
                    <li key={row.connection_id} className="flex flex-wrap gap-x-2">
                      <span className="font-medium text-foreground">{row.connection_name}</span>
                      <span>
                        {t("ai.usageConnectionRow", {
                          requests: formatNumber(row.used, locale),
                          tokens: formatNumber(
                            row.input_tokens + row.output_tokens,
                            locale,
                          ),
                          cost: formatCurrency(row.estimated_cost_usd, locale),
                        })}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {usage.recent.length > 0 ? (
              <ul className="divide-y divide-border/60 overflow-hidden rounded-md border border-border/60 bg-background/50">
                {usage.recent.slice(0, 5).map((entry) => (
                  <li
                    key={entry.id}
                    className="flex flex-wrap items-center justify-between gap-2 px-2.5 py-2 text-xs"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-medium">{entry.model}</p>
                      <p className="truncate text-2xs text-muted-foreground">
                        {entry.connection_name || entry.provider} ·{" "}
                        {formatDateTime(entry.created_at, locale)}
                      </p>
                    </div>
                    <Badge variant={entry.outcome === "success" ? "success" : "warning"}>
                      {entry.outcome === "success" ? t("ai.usageSuccess") : t("ai.usageFailed")}
                    </Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-2xs text-muted-foreground">{t("ai.usageHistoryEmpty")}</p>
            )}

            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => setHistoryOpen(true)}>
                <History className="size-icon-sm" aria-hidden="true" />
                {t("ai.usageHistoryOpen")}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive"
                disabled={clearUsage.isPending}
                onClick={clearLedger}
              >
                <Trash2 />
                {t("ai.clearUsage")}
              </Button>
            </div>
            <p className="text-2xs leading-relaxed text-muted-foreground">
              {t("ai.usageHistoryDescription")}
            </p>
          </div>
        ) : usageQuery.isError ? (
          <p className="text-2xs text-warning">{t("ai.usageUnavailable")}</p>
        ) : (
          <div className="flex items-center gap-2 text-2xs text-muted-foreground">
            <Spinner />
            {t("ai.usageLoading")}
          </div>
        )}
      </div>

      <div className="flex gap-2 rounded-lg border border-border/60 bg-background/50 p-3 text-2xs leading-relaxed text-muted-foreground">
        <ShieldCheck className="mt-0.5 size-icon-sm shrink-0 text-success" aria-hidden="true" />
        <p>{t("ai.privacy")}</p>
      </div>

      {connectionsQuery.isError ? (
        <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/5 p-3 text-xs">
          <CircleAlert className="mt-0.5 size-icon-sm shrink-0 text-warning" aria-hidden="true" />
          <div className="space-y-1">
            <p>{t("ai.connectionsError")}</p>
            <Button variant="outline" size="sm" onClick={() => void connectionsQuery.refetch()}>
              {tCommon("actions.retry")}
            </Button>
          </div>
        </div>
      ) : null}

      <AiUsageHistoryDialog open={historyOpen} onOpenChange={setHistoryOpen} />
    </SettingsSection>
  );
}
