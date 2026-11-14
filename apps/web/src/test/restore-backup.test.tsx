import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProjectDetail } from "@docurebuild/shared-types";

import { RestoreBackupDialog } from "@/components/projects/restore-backup-dialog";
import { i18n, initI18n } from "@/i18n";

const mocks = vi.hoisted(() => ({
  restore: vi.fn(),
  maxMb: 10,
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("sonner", () => ({ toast: mocks.toast }));

vi.mock("@/hooks/use-app", () => ({
  useAppMeta: () => ({ data: { max_backup_mb: mocks.maxMb } }),
}));

vi.mock("@/hooks/use-projects", () => ({
  useRestoreProjectBackup: () => ({
    isPending: false,
    mutate: mocks.restore,
  }),
}));

const restored: ProjectDetail = {
  id: "restored-1",
  name: "Quantum Mechanics (restored)",
  description: "Reference book",
  page_count: 3,
  directory: "/tmp/restored-1",
  created_at: "2026-11-01T00:00:00Z",
  updated_at: "2026-11-12T00:00:00Z",
  last_opened_at: "2026-11-12T00:00:00Z",
  document_updated_at: "2026-11-12T00:00:00Z",
};

function renderDialog() {
  const onRestored = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <RestoreBackupDialog
      open
      onOpenChange={onOpenChange}
      onRestored={onRestored}
    />,
  );
  return { onRestored, onOpenChange };
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
  mocks.maxMb = 10;
  mocks.restore.mockReset();
  mocks.toast.success.mockReset();
  mocks.toast.error.mockReset();
});

describe("RestoreBackupDialog", () => {
  it("rejects files that are not backup archives", () => {
    renderDialog();

    chooseFile(new File(["content"], "backup.tar"));

    expect(
      screen.getByText("Choose a .zip or .drbz backup created by DocuRebuild."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Restore project" })).toBeDisabled();
  });

  it("rejects a backup larger than the configured limit", () => {
    renderDialog();

    const large = new File(["x"], "large.zip");
    Object.defineProperty(large, "size", { value: 11 * 1024 * 1024 });
    chooseFile(large);

    expect(
      screen.getByText("This backup is larger than the 10 MB limit."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Restore project" })).toBeDisabled();
  });

  it("restores a selected archive as a new project", async () => {
    mocks.restore.mockImplementation((_input: { file: File; password?: string }, options: {
      onSuccess: (project: ProjectDetail) => void;
    }) => options.onSuccess(restored));
    const { onRestored, onOpenChange } = renderDialog();

    const file = new File(["zip"], "book.zip", { type: "application/zip" });
    chooseFile(file);
    expect(screen.getByText("book.zip")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Restore project" }));

    await waitFor(() => expect(onRestored).toHaveBeenCalledWith(restored));
    // A plain zip is restored without a password, so none is sent.
    expect(mocks.restore).toHaveBeenCalledWith(
      { file, password: undefined },
      expect.any(Object),
    );
    expect(mocks.toast.success).toHaveBeenCalledWith(
      "“Quantum Mechanics (restored)” was restored as a new project.",
    );
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("accepts an encrypted .drbz archive and sends its password", async () => {
    mocks.restore.mockImplementation((_input: { file: File; password?: string }, options: {
      onSuccess: (project: ProjectDetail) => void;
    }) => options.onSuccess(restored));
    renderDialog();

    const file = new File(["DRBZ"], "book-backup.drbz");
    chooseFile(file);
    expect(screen.getByText("book-backup.drbz")).toBeInTheDocument();

    fireEvent.change(
      screen.getByLabelText("Password (only for an encrypted backup)"),
      { target: { value: "correct horse battery" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Restore project" }));

    await waitFor(() =>
      expect(mocks.restore).toHaveBeenCalledWith(
        { file, password: "correct horse battery" },
        expect.any(Object),
      ),
    );
  });

  it("shows an error when the restore fails", async () => {
    mocks.restore.mockImplementation((_input: { file: File; password?: string }, options: {
      onError: (error: Error) => void;
    }) => options.onError(new Error("failed")));
    const { onRestored } = renderDialog();

    chooseFile(new File(["zip"], "book.zip", { type: "application/zip" }));
    fireEvent.click(screen.getByRole("button", { name: "Restore project" }));

    await waitFor(() => expect(mocks.toast.error).toHaveBeenCalled());
    expect(onRestored).not.toHaveBeenCalled();
  });
});
