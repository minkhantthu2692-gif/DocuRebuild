import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { SettingsPage } from "@/pages/settings-page";
import { i18n, initI18n } from "@/i18n";

const mocks = vi.hoisted(() => ({
  update: vi.fn(),
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
  backups: { auto_on_open: false, interval_hours: 24, keep_copies: 5 },
};

vi.mock("@/hooks/use-app", () => ({
  useAppMeta: () => ({ data: undefined }),
  useAppSettings: () => ({ data: settings, isLoading: false }),
  useHealth: () => ({ data: undefined }),
  useUpdateSettings: () => ({ mutate: mocks.update, isPending: false }),
}));

vi.mock("@/hooks/use-ai", () => ({
  useAiProviders: () => ({ data: undefined, isLoading: false }),
  useAiConnections: () => ({
    data: undefined,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
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
});

describe("backup settings", () => {
  it("shows the local backup section with current interval and retention", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "Backup copies" })).toBeInTheDocument();
    expect(screen.getByText("1 day")).toBeInTheDocument();
    expect(screen.getByText("5 copies")).toBeInTheDocument();
    expect(
      screen.getByText(/The optional scheduled command uses the same setting/),
    ).toBeInTheDocument();
  });

  it("opts in to automatic copies without saving any other section", () => {
    renderPage();

    fireEvent.click(
      screen.getByLabelText("Create automatic backup copies when one is due"),
    );

    expect(mocks.update).toHaveBeenCalledWith(
      { backups: { auto_on_open: true } },
      expect.any(Object),
    );
  });
});
