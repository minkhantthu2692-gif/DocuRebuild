import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { BackupSelection } from "@docurebuild/shared-types";

import { RestorePagesDialog } from "@/components/workspace/restore-pages-dialog";
import { i18n, initI18n } from "@/i18n";
import { ApiError } from "@/lib/api";

const mocks = vi.hoisted(() => ({
  backups: {
    isPending: false,
    isError: false,
    error: null as unknown,
    data: [] as Array<{ filename: string; byte_size: number; created_at: string }>,
  },
  inspectCopy: vi.fn(),
  inspectUpload: vi.fn(),
  restore: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("sonner", () => ({ toast: mocks.toast }));

vi.mock("@/hooks/use-app", () => ({
  useAppMeta: () => ({ data: { max_backup_mb: 10 } }),
}));

vi.mock("@/hooks/use-projects", () => ({
  useProjectBackups: () => mocks.backups,
  useInspectStoredBackup: () => ({
    isPending: false,
    mutate: mocks.inspectCopy,
  }),
  useInspectUploadedBackup: () => ({
    isPending: false,
    mutate: mocks.inspectUpload,
  }),
  useRestoreSelectedPages: () => ({
    isPending: false,
    mutate: mocks.restore,
  }),
}));

const selection: BackupSelection = {
  token: "a".repeat(32),
  source_name: "book-20261112.zip",
  created_at: "2026-11-12T00:00:00Z",
  pages: [
    {
      id: "page-1",
      page_number: 1,
      source_kind: "image",
      status: "ready",
      width: 1200,
      height: 800,
      original_filename: "page-1.png",
    },
    {
      id: "page-2",
      page_number: 2,
      source_kind: "image",
      status: "ready",
      width: 1200,
      height: 800,
      original_filename: "page-2.png",
    },
  ],
};

function renderDialog() {
  const onOpenChange = vi.fn();
  const onRestored = vi.fn();
  render(
    <RestorePagesDialog
      projectId="project-1"
      open
      onOpenChange={onOpenChange}
      onRestored={onRestored}
    />,
  );
  return { onOpenChange, onRestored };
}

function chooseFile(file: File) {
  fireEvent.change(screen.getByLabelText("Choose backup file"), {
    target: { files: [file] },
  });
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
    data: [
      {
        filename: "book-20261112.zip",
        byte_size: 2048,
        created_at: "2026-11-12T00:00:00Z",
      },
    ],
  };
  mocks.inspectCopy.mockReset();
  mocks.inspectUpload.mockReset();
  mocks.restore.mockReset();
  mocks.toast.success.mockReset();
  mocks.toast.error.mockReset();
});

describe("RestorePagesDialog", () => {
  it("inspects a stored copy, selects a page and appends it", async () => {
    mocks.inspectCopy.mockImplementation(
      (_input: { projectId: string; filename: string }, options: {
        onSuccess: (result: BackupSelection) => void;
      }) => options.onSuccess(selection),
    );
    mocks.restore.mockImplementation(
      (_input: { token: string; pageIds: string[] }, options: {
        onSuccess: (result: { restored: number; page_numbers: number[] }) => void;
      }) => options.onSuccess({ restored: 1, page_numbers: [3] }),
    );
    const { onOpenChange, onRestored } = renderDialog();

    fireEvent.click(screen.getByRole("radio", { name: /book-20261112\.zip/ }));
    fireEvent.click(screen.getByRole("button", { name: "Inspect backup" }));

    expect(mocks.inspectCopy).toHaveBeenCalledWith(
      { projectId: "project-1", filename: "book-20261112.zip" },
      expect.any(Object),
    );
    expect(screen.getByText("Pages in this backup")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("checkbox", { name: "Restore page 1" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Restore 1 page" }));

    await waitFor(() =>
      expect(mocks.restore).toHaveBeenCalledWith(
        { token: selection.token, pageIds: ["page-1"] },
        expect.any(Object),
      ),
    );
    expect(mocks.toast.success).toHaveBeenCalledWith(
      "Restored 1 page to this project.",
    );
    expect(onRestored).toHaveBeenCalledWith({ restored: 1, page_numbers: [3] });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("keeps the restore action disabled until a page is chosen", () => {
    mocks.inspectCopy.mockImplementation(
      (_input: unknown, options: { onSuccess: (result: BackupSelection) => void }) =>
        options.onSuccess(selection),
    );
    renderDialog();

    fireEvent.click(screen.getByRole("radio", { name: /book-20261112\.zip/ }));
    fireEvent.click(screen.getByRole("button", { name: "Inspect backup" }));

    expect(screen.getByText("Select at least one page to restore.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Restore pages" })).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox", { name: "Select all pages" }));
    expect(screen.getByRole("button", { name: "Restore 2 pages" })).toBeEnabled();
  });

  it("inspects an uploaded encrypted archive with its password", () => {
    mocks.inspectUpload.mockImplementation(
      (_input: { projectId: string; file: File; password?: string }, options: {
        onSuccess: (result: BackupSelection) => void;
      }) => options.onSuccess(selection),
    );
    renderDialog();

    fireEvent.click(screen.getByText("Uploaded file"));
    const file = new File(["DRBZ"], "book.drbz");
    chooseFile(file);
    fireEvent.change(
      screen.getByLabelText("Password (only for an encrypted backup)"),
      { target: { value: "correct horse battery" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Inspect backup" }));

    expect(mocks.inspectUpload).toHaveBeenCalledWith(
      { projectId: "project-1", file, password: "correct horse battery" },
      expect.any(Object),
    );
    expect(screen.getByText("Pages in this backup")).toBeInTheDocument();
  });

  it("rejects files that are not backup archives", () => {
    renderDialog();

    fireEvent.click(screen.getByText("Uploaded file"));
    chooseFile(new File(["content"], "backup.tar"));

    expect(
      screen.getByText("Choose a .zip or .drbz backup created by DocuRebuild."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Inspect backup" })).toBeDisabled();
  });

  it("clears the page list when the selection expires", async () => {
    mocks.inspectCopy.mockImplementation(
      (_input: unknown, options: { onSuccess: (result: BackupSelection) => void }) =>
        options.onSuccess(selection),
    );
    mocks.restore.mockImplementation(
      (_input: unknown, options: { onError: (error: Error) => void }) =>
        options.onError(
          new ApiError(
            "restore_selection_expired",
            "This page selection has expired. Inspect the backup again.",
            410,
          ),
        ),
    );
    renderDialog();

    fireEvent.click(screen.getByRole("radio", { name: /book-20261112\.zip/ }));
    fireEvent.click(screen.getByRole("button", { name: "Inspect backup" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select all pages" }));
    fireEvent.click(screen.getByRole("button", { name: "Restore 2 pages" }));

    await waitFor(() =>
      expect(
        screen.getByText("This page selection has expired. Inspect the backup again."),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText("Pages in this backup")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Restore pages" })).toBeDisabled();
  });
});
