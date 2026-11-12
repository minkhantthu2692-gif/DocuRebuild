import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  DocumentRecord,
  DocumentRevision,
  DocumentRevisionSummary,
} from "@docurebuild/shared-types";

import { RevisionDialog } from "@/components/workspace/revision-dialog";
import { i18n, initI18n } from "@/i18n";

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  restore: vi.fn(),
  refetch: vi.fn(),
  revisions: [] as DocumentRevisionSummary[],
  detail: null as DocumentRevision | null,
  isLoading: false,
  isError: false,
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("sonner", () => ({ toast: mocks.toast }));

vi.mock("@/hooks/use-document", () => ({
  useDocumentRevisions: () => ({
    data: mocks.revisions,
    isLoading: mocks.isLoading,
    isError: mocks.isError,
    isFetching: false,
    refetch: mocks.refetch,
  }),
  useDocumentRevision: (_projectId: string, revisionId: string | null) => ({
    data: revisionId ? mocks.detail : undefined,
    isLoading: false,
    isError: false,
  }),
  useCreateDocumentRevision: () => ({ isPending: false, mutateAsync: mocks.create }),
  useRestoreDocumentRevision: () => ({ isPending: false, mutateAsync: mocks.restore }),
}));

const revision: DocumentRevisionSummary = {
  id: "revision-1",
  source: "autosave",
  preview: "Earlier chapter text",
  character_count: 20,
  created_at: "2026-11-10T09:30:00Z",
};

// The detail call returns the full text, not the 200-character list preview.
const revisionDetail: DocumentRevision = {
  ...revision,
  content: {
    type: "doc",
    content: [
      {
        type: "paragraph",
        content: [{ type: "text", text: "Earlier chapter text" }],
      },
      {
        type: "paragraph",
        content: [{ type: "text", text: "Uncertain table cell kept as typed" }],
      },
    ],
  },
  plain_text: "Earlier chapter text\n\nUncertain table cell kept as typed",
};

const manualRevision: DocumentRevisionSummary = {
  id: "revision-2",
  source: "manual",
  preview: "",
  character_count: 0,
  created_at: "2026-11-10T10:00:00Z",
};

const restored: DocumentRecord = {
  format: "tiptap",
  schema_version: 1,
  content: { type: "doc", content: [{ type: "paragraph" }] },
  plain_text: "",
  updated_at: "2026-11-10T10:05:00Z",
};

function renderDialog(
  ensureSaved = vi.fn().mockResolvedValue(true),
  currentText = revisionDetail.plain_text,
) {
  const onRestored = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <RevisionDialog
      projectId="project-1"
      open
      onOpenChange={onOpenChange}
      currentText={currentText}
      ensureSaved={ensureSaved}
      onRestored={onRestored}
    />,
  );
  return { ensureSaved, onRestored, onOpenChange };
}

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

beforeEach(() => {
  mocks.revisions = [revision, manualRevision];
  mocks.detail = revisionDetail;
  mocks.isLoading = false;
  mocks.isError = false;
  mocks.create.mockReset().mockResolvedValue(manualRevision);
  mocks.restore.mockReset().mockResolvedValue(restored);
  mocks.refetch.mockReset();
  mocks.toast.success.mockReset();
  mocks.toast.error.mockReset();
});

describe("RevisionDialog", () => {
  it("lists versions with their source and a text preview", () => {
    renderDialog();

    expect(screen.getByText("Versions: 2")).toBeInTheDocument();
    expect(screen.getByText("Earlier chapter text")).toBeInTheDocument();
    expect(screen.getByText("Automatic")).toBeInTheDocument();
    expect(screen.getByText("Checkpoint")).toBeInTheDocument();
    expect(screen.getByText("This version has no text.")).toBeInTheDocument();
  });

  it("requires confirmation and saves pending edits before restoring", async () => {
    const { ensureSaved, onRestored, onOpenChange } = renderDialog();

    fireEvent.click(screen.getAllByRole("button", { name: "Restore" })[0]);
    expect(mocks.restore).not.toHaveBeenCalled();
    expect(
      screen.getByText(/The current document is kept as a version first/),
    ).toBeInTheDocument();
    // The exact stored text is shown before the restore, not just the list preview.
    expect(screen.getByText("Version text")).toBeInTheDocument();
    expect(
      screen.getByText(/Uncertain table cell kept as typed/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Restore version" }));

    await waitFor(() => expect(onRestored).toHaveBeenCalledWith(restored));
    expect(ensureSaved).toHaveBeenCalledTimes(1);
    expect(mocks.restore).toHaveBeenCalledWith("revision-1");
    expect(mocks.toast.success).toHaveBeenCalledWith("Version restored.");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("does not restore when unsaved edits cannot be saved", async () => {
    const ensureSaved = vi.fn().mockResolvedValue(false);
    const { onRestored } = renderDialog(ensureSaved);

    fireEvent.click(screen.getAllByRole("button", { name: "Restore" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Restore version" }));

    await waitFor(() => expect(mocks.toast.error).toHaveBeenCalled());
    expect(mocks.restore).not.toHaveBeenCalled();
    expect(onRestored).not.toHaveBeenCalled();
  });

  it("compares a version with the on-screen text without saving or restoring", () => {
    const { ensureSaved } = renderDialog(
      undefined,
      "Earlier chapter text\n\nRewritten paragraph\n\nA new line",
    );

    fireEvent.click(screen.getAllByRole("button", { name: "Compare" })[0]);

    expect(screen.getByText("Compared with the current document")).toBeInTheDocument();
    expect(screen.getByText("1 line removed")).toBeInTheDocument();
    expect(screen.getByText("3 lines added")).toBeInTheDocument();
    expect(screen.getByText("Uncertain table cell kept as typed")).toBeInTheDocument();
    expect(screen.getByText("Rewritten paragraph")).toBeInTheDocument();
    expect(screen.getByText("A new line")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Close comparison" }),
    ).toBeInTheDocument();

    // Comparison is read-only: no save flush and no restore request.
    expect(ensureSaved).not.toHaveBeenCalled();
    expect(mocks.restore).not.toHaveBeenCalled();
  });

  it("reports when a version matches the current document", () => {
    renderDialog();

    fireEvent.click(screen.getAllByRole("button", { name: "Compare" })[0]);

    expect(
      screen.getByText("No differences. This version matches the current document."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/lines? added/)).not.toBeInTheDocument();
  });

  it("saves a checkpoint of the visible document", async () => {
    const { ensureSaved } = renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Save version" }));

    await waitFor(() => expect(mocks.create).toHaveBeenCalledTimes(1));
    expect(ensureSaved).toHaveBeenCalledTimes(1);
    expect(mocks.toast.success).toHaveBeenCalledWith("Version saved.");
  });
});
