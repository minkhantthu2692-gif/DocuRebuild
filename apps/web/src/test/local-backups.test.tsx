import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { LocalBackupsDialog } from "@/components/workspace/local-backups-dialog";
import { i18n, initI18n } from "@/i18n";

const mocks = vi.hoisted(() => ({
  backups: {
    isPending: false,
    isError: false,
    error: null as unknown,
    data: [] as Array<{ filename: string; byte_size: number; created_at: string }>,
  },
  create: vi.fn(),
  download: vi.fn(),
  deleteCopy: vi.fn(),
  saveBlob: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("sonner", () => ({ toast: mocks.toast }));

vi.mock("@/hooks/use-projects", () => ({
  useProjectBackups: () => mocks.backups,
  useCreateProjectBackupCopy: () => ({
    isPending: false,
    mutate: mocks.create,
  }),
  useDownloadProjectBackupCopy: () => ({
    isPending: false,
    variables: undefined,
    mutate: mocks.download,
  }),
  useDeleteProjectBackupCopy: () => ({
    isPending: false,
    variables: undefined,
    mutate: mocks.deleteCopy,
  }),
}));

vi.mock("@/lib/download", () => ({ saveBlob: mocks.saveBlob }));

function renderDialog() {
  const onOpenChange = vi.fn();
  render(
    <LocalBackupsDialog projectId="project-1" open onOpenChange={onOpenChange} />,
  );
  return { onOpenChange };
}

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

beforeEach(() => {
  mocks.backups = {
    isPending: false,
    isError: false,
    error: null,
    data: [],
  };
  mocks.create.mockReset();
  mocks.download.mockReset();
  mocks.deleteCopy.mockReset();
  mocks.saveBlob.mockReset();
  mocks.toast.success.mockReset();
  mocks.toast.error.mockReset();
});

describe("LocalBackupsDialog", () => {
  it("lists stored copies with size and downloads the chosen one", async () => {
    mocks.backups.data = [
      {
        filename: "Book-20261113-101500.zip",
        byte_size: 1536,
        created_at: "2026-11-13T10:15:00+00:00",
      },
    ];
    mocks.download.mockImplementation(
      (
        _variables: { projectId: string; filename: string },
        options: { onSuccess: (result: { blob: Blob; filename: string }) => void },
      ) => options.onSuccess({ blob: new Blob(["zip"]), filename: "Book-20261113-101500.zip" }),
    );
    renderDialog();

    expect(screen.getByText("Book-20261113-101500.zip")).toBeInTheDocument();
    expect(screen.getByText(/1\.5 KB/)).toBeInTheDocument();
    expect(
      screen.getByText(/Copies are pruned automatically/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Download backup copy" }));

    await waitFor(() =>
      expect(mocks.download).toHaveBeenCalledWith(
        { projectId: "project-1", filename: "Book-20261113-101500.zip" },
        expect.any(Object),
      ),
    );
    expect(mocks.saveBlob).toHaveBeenCalled();
    expect(mocks.toast.success).toHaveBeenCalledWith("Backup copy downloaded");
  });

  it("creates a copy from the empty state", async () => {
    renderDialog();

    expect(screen.getByText("No local copies yet")).toBeInTheDocument();
    mocks.create.mockImplementation(
      (_input: undefined, options: { onSuccess: () => void }) => options.onSuccess(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Create copy" }));

    await waitFor(() => expect(mocks.create).toHaveBeenCalled());
    expect(mocks.toast.success).toHaveBeenCalledWith("Backup copy created");
  });

  it("asks for confirmation before deleting one copy", async () => {
    mocks.backups.data = [
      {
        filename: "Book-20261113-101500.zip",
        byte_size: 1536,
        created_at: "2026-11-13T10:15:00+00:00",
      },
    ];
    mocks.deleteCopy.mockImplementation(
      (_filename: string, options: { onSuccess: () => void }) =>
        options.onSuccess(),
    );
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Delete backup copy" }));

    expect(screen.getByText("Delete this backup copy?")).toBeInTheDocument();
    expect(mocks.deleteCopy).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Delete copy" }));

    await waitFor(() =>
      expect(mocks.deleteCopy).toHaveBeenCalledWith(
        "Book-20261113-101500.zip",
        expect.any(Object),
      ),
    );
    expect(mocks.toast.success).toHaveBeenCalledWith("Backup copy deleted");
  });

  it("shows an error when the list cannot be loaded", () => {
    mocks.backups = {
      ...mocks.backups,
      isError: true,
      error: new Error("failed"),
    };
    renderDialog();

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("No local copies yet")).not.toBeInTheDocument();
  });
});
