import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import type {
  AiConnection,
  AiConnectionDetail,
  AiKey,
  AiModel,
  AiProviderInfo,
  AiTaskRoute,
  AiUsageResponse,
} from "@docurebuild/shared-types";

import { SettingsPage } from "@/pages/settings-page";
import { i18n, initI18n } from "@/i18n";

const mocks = vi.hoisted(() => ({
  update: vi.fn(),
  createConnection: vi.fn(),
  updateConnection: vi.fn(),
  testConnection: vi.fn(),
  addKey: vi.fn(),
  updateKey: vi.fn(),
  deleteKey: vi.fn(),
  addModel: vi.fn(),
  favoriteModel: vi.fn(),
  updateRoute: vi.fn(),
  updatePreferences: vi.fn(),
  clearUsage: vi.fn(),
  connections: [] as AiConnection[],
  connectionDetail: null as AiConnectionDetail | null,
  providers: [] as AiProviderInfo[],
  models: [] as AiModel[],
  routes: [] as AiTaskRoute[],
  preferences: { daily_request_limit: 0, monthly_budget_usd: null as number | null },
  usage: null as AiUsageResponse | null,
}));

const settings = {
  language: "en" as const,
  appearance: {
    theme: "system" as const,
    accent: "indigo" as const,
    radius: "soft" as const,
    blur: "subtle" as const,
    density: "comfortable" as const,
    font_size: "md" as const,
    motion: "full" as const,
  },
  editor: { document_font: "serif" as const },
  export: { pdf_page_size: "a4" as const, pdf_margin: "normal" as const },
  backups: { auto_on_open: false, interval_hours: 24, keep_copies: 5 },
};

vi.mock("@/hooks/use-app", () => ({
  useAppMeta: () => ({ data: undefined }),
  useAppSettings: () => ({ data: settings, isLoading: false }),
  useHealth: () => ({ data: undefined }),
  useUpdateSettings: () => ({ mutate: mocks.update, isPending: false }),
}));

vi.mock("@/hooks/use-ai", () => ({
  useAiProviders: () => ({ data: { providers: mocks.providers }, isLoading: false }),
  useAiConnections: () => ({
    data: { connections: mocks.connections },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useAiConnection: () => ({ data: mocks.connectionDetail, isLoading: false }),
  useAiOverview: () => ({
    data: {
      connection_count: mocks.connections.length,
      enabled_connection_count: mocks.connections.filter((item) => item.enabled).length,
      key_count: mocks.connections.reduce((total, item) => total + item.key_count, 0),
      model_count: mocks.models.length,
      configured_task_count: mocks.routes.filter((route) => route.configured).length,
      task_count: 4,
      preferences: mocks.preferences,
    },
  }),
  useAiPreferences: () => ({ data: mocks.preferences }),
  useAiUsage: () => ({ data: mocks.usage, isError: false }),
  useAiRoutes: () => ({ data: { routes: mocks.routes, default_model: null }, isLoading: false }),
  useAiMigration: () => ({ data: { needed: false, migrated: true, completed_at: null, detail: null } }),
  useAiModels: () => ({ data: mocks.models, isLoading: false }),
  useAiUsageHistory: () => ({ data: undefined, isLoading: false, isError: false }),
  useCreateAiConnection: () => ({
    mutate: mocks.createConnection,
    mutateAsync: vi.fn(),
    isPending: false,
  }),
  useUpdateAiConnection: () => ({ mutate: mocks.updateConnection, isPending: false }),
  useDeleteAiConnection: () => ({ mutate: vi.fn(), isPending: false }),
  useTestAiConnection: () => ({ mutate: mocks.testConnection, isPending: false }),
  useAddAiKey: () => ({ mutate: mocks.addKey, isPending: false }),
  useUpdateAiKey: () => ({ mutate: mocks.updateKey, isPending: false }),
  useDeleteAiKey: () => ({ mutate: mocks.deleteKey, isPending: false }),
  useAddAiModel: () => ({ mutate: mocks.addModel, isPending: false }),
  useFavoriteAiModel: () => ({ mutate: mocks.favoriteModel, isPending: false }),
  useUpdateAiRoute: () => ({ mutate: mocks.updateRoute, isPending: false }),
  useUpdateAiPreferences: () => ({ mutate: mocks.updatePreferences, isPending: false }),
  useClearAiUsage: () => ({ mutate: mocks.clearUsage, isPending: false }),
}));

vi.mock("@/hooks/use-ocr", () => ({
  useOcrCapabilities: () => ({ data: undefined, isLoading: false, isFetching: false }),
}));

function provider(): AiProviderInfo {
  return {
    id: "openai",
    name: "OpenAI",
    kind: "openai",
    default_base_url: "https://api.openai.com/v1",
    requires_base_url: false,
    supports_model_discovery: true,
    allows_manual_models: false,
    local_default: false,
    requires_api_key: true,
    docs_url: null,
  };
}

function connection(patch: Partial<AiConnection> = {}): AiConnection {
  return {
    id: "conn-1",
    provider: "openai",
    provider_name: "OpenAI",
    provider_kind: "openai",
    name: "Personal OpenAI",
    base_url: "https://api.openai.com/v1",
    allow_remote: true,
    cost_class: "paid",
    enabled: true,
    rotation_strategy: "priority",
    max_attempts: 3,
    request_limit: 0,
    monthly_budget_usd: null,
    settings: {},
    status: "connected",
    last_error_code: null,
    last_http_status: null,
    retry_after_seconds: null,
    last_checked_at: "2026-11-19T09:00:00",
    created_at: "2026-11-18T09:00:00",
    updated_at: "2026-11-18T09:00:00",
    key_count: 1,
    enabled_key_count: 1,
    model_count: 2,
    requires_api_key: true,
    ...patch,
  };
}

function key(): AiKey {
  return {
    id: "key-1",
    label: "Primary",
    enabled: true,
    priority: 100,
    request_limit: 0,
    auth_failed: false,
    status: "ready",
    has_secret: true,
    last_used_at: null,
    last_success_at: null,
    last_error_at: null,
    last_error_code: null,
    cooldown_until: null,
    created_at: "2026-11-18T09:00:00",
  };
}

function model(patch: Partial<AiModel> = {}): AiModel {
  return {
    id: "model-1",
    connection_id: "conn-1",
    model_id: "gpt-4o",
    display_name: "GPT-4o",
    family: "gpt",
    context_window: 128_000,
    input_modalities: ["text", "image"],
    output_modalities: ["text"],
    supports_tools: true,
    supports_streaming: true,
    pricing: null,
    metadata: null,
    source: "discovered",
    available: true,
    favorite: false,
    last_used_at: null,
    discovered_at: "2026-11-18T09:00:00",
    ...patch,
  };
}

function route(patch: Partial<AiTaskRoute> = {}): AiTaskRoute {
  return {
    task: "default",
    connection_id: "conn-1",
    connection_name: "Personal OpenAI",
    connection_status: "connected",
    cost_class: "paid",
    model_id: "gpt-4o",
    model_display_name: "GPT-4o",
    model_source: "discovered",
    capability: "text",
    fallback_connection_id: null,
    fallback_connection_name: null,
    fallback_model_id: null,
    temperature: 0.2,
    timeout_seconds: 60,
    request_limit: 0,
    configured: true,
    warnings: [],
    updated_at: "2026-11-18T09:00:00",
    ...patch,
  };
}

function usage(): AiUsageResponse {
  return {
    window_hours: 24,
    request_limit: 10,
    used: 4,
    remaining: 6,
    successful: 3,
    failed: 1,
    input_tokens: 1_200,
    output_tokens: 400,
    total_tokens: 1_600,
    estimated_cost_usd: 0.42,
    unpriced_requests: 1,
    monthly_cost_usd: 1.2,
    by_task: [
      { task: "ocr_cleanup", used: 2 },
      { task: "equation_transcription", used: 1 },
      { task: "legacy_task", used: 1 },
    ],
    by_connection: [
      {
        connection_id: "conn-1",
        connection_name: "Personal OpenAI",
        provider: "openai",
        used: 4,
        input_tokens: 1_200,
        output_tokens: 400,
        estimated_cost_usd: 0.42,
        unpriced_requests: 1,
      },
    ],
    recent: [],
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

beforeEach(() => {
  mocks.update.mockReset();
  mocks.createConnection.mockReset();
  mocks.updateConnection.mockReset();
  mocks.testConnection.mockReset();
  mocks.addKey.mockReset();
  mocks.updateKey.mockReset();
  mocks.deleteKey.mockReset();
  mocks.addModel.mockReset();
  mocks.favoriteModel.mockReset();
  mocks.updateRoute.mockReset();
  mocks.updatePreferences.mockReset();
  mocks.clearUsage.mockReset();
  mocks.connections = [connection()];
  mocks.connectionDetail = { ...connection(), keys: [key()] };
  mocks.providers = [provider()];
  mocks.models = [model()];
  mocks.routes = [route()];
  mocks.preferences = { daily_request_limit: 0, monthly_budget_usd: null };
  mocks.usage = null;
});

describe("AI provider settings", () => {
  it("lists a connection with its status and key/model counts", () => {
    renderPage();

    expect(screen.getByText("Personal OpenAI")).toBeInTheDocument();
    expect(screen.getAllByText("Connected").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/2 model\(s\) · 1 key\(s\)/).length,
    ).toBeGreaterThan(0);
  });

  it("adds an API key to the selected connection", () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Add key" }));
    fireEvent.change(screen.getByLabelText("Key label"), {
      target: { value: "Backup key" },
    });
    fireEvent.change(screen.getByLabelText("API key"), {
      target: { value: "  sk-test-key  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save key" }));

    expect(mocks.addKey).toHaveBeenCalledWith(
      {
        label: "Backup key",
        api_key: "sk-test-key",
        priority: 100,
        request_limit: 0,
      },
      expect.any(Object),
    );
  });

  it("tests the connection and reports the discovered model count", async () => {
    mocks.testConnection.mockImplementation(
      (_payload: unknown, options?: { onSuccess?: (result: unknown) => void }) => {
        options?.onSuccess?.({
          connection_id: "conn-1",
          status: "connected",
          provider: "openai",
          base_url: "https://api.openai.com/v1",
          models_found: 12,
          cached: false,
          version: null,
          error_code: null,
          http_status: 200,
          retry_after_seconds: null,
          last_checked_at: "2026-11-19T09:00:00",
          message: null,
        });
      },
    );
    renderPage();

    fireEvent.click(
      screen.getAllByRole("button", { name: "Test connection" })[0],
    );

    await waitFor(() =>
      expect(screen.getByText("12 model(s) available")).toBeInTheDocument(),
    );
  });

  it("saves the daily request limit and budget", () => {
    renderPage();

    fireEvent.change(screen.getByLabelText("Daily request limit"), {
      target: { value: "25" },
    });
    fireEvent.change(screen.getByLabelText("Monthly budget (USD)"), {
      target: { value: "5.5" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save limits" }));

    expect(mocks.updatePreferences).toHaveBeenCalledWith(
      { daily_request_limit: 25, monthly_budget_usd: 5.5 },
      expect.any(Object),
    );
  });

  it("saves a route with the full payload", () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Advanced" }));
    fireEvent.change(screen.getByLabelText("Default route: Temperature"), {
      target: { value: "0.5" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save route" }));

    expect(mocks.updateRoute).toHaveBeenCalledWith(
      {
        task: "default",
        payload: {
          connection_id: "conn-1",
          model_id: "gpt-4o",
          fallback_connection_id: null,
          fallback_model_id: null,
          temperature: 0.5,
          timeout_seconds: 60,
          request_limit: 0,
        },
      },
      expect.any(Object),
    );
  });

  it("breaks the rolling request budget down by task", () => {
    mocks.usage = usage();
    renderPage();

    expect(screen.getByText("By task, last 24 hours")).toBeInTheDocument();
    expect(screen.getByText("OCR text cleanup: 2")).toBeInTheDocument();
    expect(screen.getByText("Equation transcription: 1")).toBeInTheDocument();
    // A task name this build does not know is counted, not hidden.
    expect(screen.getByText("Other task: 1")).toBeInTheDocument();
    expect(screen.getByText(/1 request\(s\) have no verified price/)).toBeInTheDocument();
  });

  it("clears the local usage ledger after confirmation", () => {
    mocks.usage = usage();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Clear history" }));

    expect(mocks.clearUsage).toHaveBeenCalled();
  });
});
