import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { DownloadBackupDialog } from "@/components/projects/download-backup-dialog";
import { i18n, initI18n } from "@/i18n";

const mocks = vi.hoisted(() => ({
  download: vi.fn(),
  saveBlob: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("sonner", () => ({ toast: mocks.toast }));

vi.mock("@/hooks/use-projects", () => ({
  useDownloadProjectBackup: () => ({
    isPending: false,
    mutate: mocks.download,
  }),
}));

vi.mock("@/lib/download", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/download")>();
  return { ...actual, saveBlob: mocks.saveBlob };
});

function renderDialog() {
  const onOpenChange = vi.fn();
  render(
    <DownloadBackupDialog
      projectId="project-1"
      open
      onOpenChange={onOpenChange}
    />,
  );
  return { onOpenChange };
}

function chooseProtected() {
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "Protect this archive with a password",
    }),
  );
}

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

beforeEach(() => {
  mocks.download.mockReset();
  mocks.saveBlob.mockReset();
  mocks.toast.success.mockReset();
  mocks.toast.error.mockReset();
});

describe("DownloadBackupDialog", () => {
  it("downloads a plain archive when protection is off", () => {
    mocks.download.mockImplementation(
      (_input: { projectId: string; password?: string }, options: {
        onSuccess: (result: { blob: Blob; filename: string }) => void;
      }) => options.onSuccess({ blob: new Blob(["zip"]), filename: "book.zip" }),
    );
    const { onOpenChange } = renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Download" }));

    expect(mocks.download).toHaveBeenCalledWith(
      { projectId: "project-1", password: undefined },
      expect.any(Object),
    );
    expect(mocks.saveBlob).toHaveBeenCalledWith(expect.any(Blob), "book.zip");
    expect(mocks.toast.success).toHaveBeenCalledWith("Backup download started.");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("sends the confirmed password for a protected archive", () => {
    mocks.download.mockImplementation(
      (_input: { projectId: string; password?: string }, options: {
        onSuccess: (result: { blob: Blob; filename: string }) => void;
      }) => options.onSuccess({ blob: new Blob(["drbz"]), filename: "book.drbz" }),
    );
    renderDialog();

    chooseProtected();
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "correct horse battery" },
    });
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "correct horse battery" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Download" }));

    expect(mocks.download).toHaveBeenCalledWith(
      { projectId: "project-1", password: "correct horse battery" },
      expect.any(Object),
    );
    expect(mocks.saveBlob).toHaveBeenCalledWith(
      expect.any(Blob),
      "book.drbz",
    );
  });

  it("refuses a password shorter than the backend minimum", () => {
    renderDialog();

    chooseProtected();
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "short" },
    });
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "short" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Download" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Use at least 8 characters.",
    );
    expect(mocks.download).not.toHaveBeenCalled();
  });

  it("refuses mismatched passwords", () => {
    renderDialog();

    chooseProtected();
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "correct horse battery" },
    });
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "correct horse batteru" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Download" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "The two passwords do not match.",
    );
    expect(mocks.download).not.toHaveBeenCalled();
  });

  it("reports a failed download without closing", async () => {
    mocks.download.mockImplementation(
      (_input: { projectId: string; password?: string }, options: {
        onError: (error: Error) => void;
      }) => options.onError(new Error("failed")),
    );
    const { onOpenChange } = renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Download" }));

    await waitFor(() => expect(mocks.toast.error).toHaveBeenCalled());
    expect(mocks.saveBlob).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalled();
  });
});
