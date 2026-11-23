import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import type { ProjectSummary } from "@docurebuild/shared-types";

import { DashboardPage } from "@/pages/dashboard-page";
import { i18n, initI18n } from "@/i18n";

const mocks = vi.hoisted(() => ({
  bulkDelete: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
  projects: [] as ProjectSummary[],
}));

vi.mock("sonner", () => ({ toast: mocks.toast }));

vi.mock("@/hooks/use-projects", () => ({
  useProjects: () => ({ data: mocks.projects, isLoading: false, isError: false }),
  useCreateProject: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateProject: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteProject: () => ({ mutate: vi.fn(), isPending: false }),
  useDownloadProjectBackup: () => ({ mutate: vi.fn(), isPending: false }),
  useRestoreProjectBackup: () => ({ mutate: vi.fn(), isPending: false }),
  useBulkDeleteProjects: () => ({ mutate: mocks.bulkDelete, isPending: false }),
}));

vi.mock("@/hooks/use-app", () => ({
  useAppMeta: () => ({ data: { max_backup_mb: 10 } }),
}));

function project(id: string, name: string): ProjectSummary {
  return {
    id,
    name,
    description: "",
    page_count: 2,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    last_opened_at: null,
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function enterSelection() {
  fireEvent.click(screen.getByRole("button", { name: "Select" }));
}

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

beforeEach(() => {
  mocks.projects = [project("p1", "Alpha"), project("p2", "Beta"), project("p3", "Gamma")];
  mocks.bulkDelete.mockReset();
  mocks.toast.success.mockReset();
  mocks.toast.error.mockReset();
});

describe("dashboard bulk selection", () => {
  it("selects and deselects every visible project", () => {
    renderPage();
    enterSelection();

    expect(screen.getByText("0 selected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete (0)" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Select all" }));
    expect(screen.getByText("3 selected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete (3)" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Select all" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Deselect all" }));
    expect(screen.getByText("0 selected")).toBeInTheDocument();
  });

  it("toggles a single project with an accessible pressed state", () => {
    renderPage();
    enterSelection();

    const alpha = screen.getByRole("button", { name: "Select Alpha" });
    expect(alpha).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(alpha);
    expect(alpha).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("1 selected")).toBeInTheDocument();

    fireEvent.click(alpha);
    expect(alpha).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("0 selected")).toBeInTheDocument();
  });

  it("moves only the selected projects to the trash after confirmation", () => {
    mocks.bulkDelete.mockImplementation(
      (ids: string[], options: { onSuccess: (result: unknown) => void }) =>
        options.onSuccess({
          deleted: ids,
          failed: [],
          trash_paths: ids.map((id) => `/trash/${id}`),
        }),
    );
    renderPage();
    enterSelection();

    fireEvent.click(screen.getByRole("button", { name: "Select Alpha" }));
    fireEvent.click(screen.getByRole("button", { name: "Select Gamma" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete (2)" }));

    expect(screen.getByRole("heading", { name: "Delete 2 projects?" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Move 2 to trash" }));

    expect(mocks.bulkDelete).toHaveBeenCalledWith(["p1", "p3"], expect.any(Object));
    expect(mocks.toast.success).toHaveBeenCalledWith(
      "2 projects moved to the local trash folder.",
    );
    // A fully successful delete leaves selection mode, so stray ids are not kept.
    expect(screen.queryByText("2 selected")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Select" })).toBeInTheDocument();
  });

  it("keeps projects selected when the backend reports a partial failure", () => {
    mocks.bulkDelete.mockImplementation(
      (ids: string[], options: { onSuccess: (result: unknown) => void }) =>
        options.onSuccess({
          deleted: ids.slice(0, 1),
          failed: [{ id: ids[1], code: "project_delete_failed", message: "no" }],
          trash_paths: [],
        }),
    );
    renderPage();
    enterSelection();

    fireEvent.click(screen.getByRole("button", { name: "Select Alpha" }));
    fireEvent.click(screen.getByRole("button", { name: "Select Beta" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete (2)" }));
    fireEvent.click(screen.getByRole("button", { name: "Move 2 to trash" }));

    expect(mocks.toast.error).toHaveBeenCalledWith("1 moved. 1 could not be deleted.");
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Select Beta" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
