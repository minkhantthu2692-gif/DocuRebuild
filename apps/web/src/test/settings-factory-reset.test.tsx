import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { clearClientCaches } from "@/lib/client-caches";
import { SettingsPage } from "@/pages/settings-page";
import { i18n, initI18n, LANGUAGE_STORAGE_KEY } from "@/i18n";
import { APPEARANCE_STORAGE_KEY } from "@/lib/appearance";
import { WORKSPACE_LAYOUT_KEY } from "@/lib/workspace-layout";

const mocks = vi.hoisted(() => ({
  reset: vi.fn(),
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
  useHealth: () => ({
    data: { status: "ok", version: "1.0.0", database: "ok", data_dir: "C:\\Data", projects: 2 },
  }),
  useUpdateSettings: () => ({ mutate: vi.fn(), isPending: false }),
  useFactoryReset: () => ({ mutate: mocks.reset, isPending: false }),
}));

vi.mock("@/hooks/use-ai", () => ({
  useAiProviders: () => ({ data: undefined, isLoading: false }),
  useAiConnections: () => ({ data: undefined, isLoading: false, isError: false, refetch: vi.fn() }),
  useAiConnection: () => ({ data: undefined }),
  useAiOverview: () => ({ data: undefined }),
  useAiPreferences: () => ({ data: undefined }),
  useAiUsage: () => ({ data: undefined, isError: false }),
  useAiRoutes: () => ({ data: undefined, isLoading: false }),
  useAiMigration: () => ({ data: undefined }),
  useAiModels: () => ({ data: [], isLoading: false }),
  useAiUsageHistory: () => ({ data: undefined, isLoading: false, isError: false }),
  useCreateAiConnection: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useUpdateAiConnection: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteAiConnection: () => ({ mutate: vi.fn(), isPending: false }),
  useTestAiConnection: () => ({ mutate: vi.fn(), isPending: false }),
  useAddAiKey: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateAiKey: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteAiKey: () => ({ mutate: vi.fn(), isPending: false }),
  useAddAiModel: () => ({ mutate: vi.fn(), isPending: false }),
  useFavoriteAiModel: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateAiRoute: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateAiPreferences: () => ({ mutate: vi.fn(), isPending: false }),
  useClearAiUsage: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/hooks/use-ocr", () => ({
  useOcrCapabilities: () => ({ data: undefined, isLoading: false, isFetching: false }),
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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
  mocks.reset.mockReset();
  localStorage.clear();
});

describe("factory reset", () => {
  it("requires the exact confirmation word before it can run", () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Clear all data…" }));
    expect(screen.getByRole("heading", { name: "Clear all data?" })).toBeInTheDocument();
    expect(screen.getByText("This cannot be undone.")).toBeInTheDocument();

    const confirm = screen.getByRole("button", { name: "Clear all data" });
    expect(confirm).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Type DELETE to confirm"), {
      target: { value: "delete" },
    });
    expect(confirm).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Type DELETE to confirm"), {
      target: { value: "DELETE" },
    });
    expect(confirm).toBeEnabled();
  });

  it("sends the typed confirmation to the local API", () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Clear all data…" }));
    fireEvent.change(screen.getByLabelText("Type DELETE to confirm"), {
      target: { value: "DELETE" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Clear all data" }));

    expect(mocks.reset).toHaveBeenCalledWith("DELETE", expect.any(Object));
  });

  it("can clear the renderer preferences kept outside the database", () => {
    localStorage.setItem(APPEARANCE_STORAGE_KEY, "{}");
    localStorage.setItem(LANGUAGE_STORAGE_KEY, "my");
    localStorage.setItem(WORKSPACE_LAYOUT_KEY, "{}");

    clearClientCaches();

    expect(localStorage.getItem(APPEARANCE_STORAGE_KEY)).toBeNull();
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBeNull();
    expect(localStorage.getItem(WORKSPACE_LAYOUT_KEY)).toBeNull();
  });
});
