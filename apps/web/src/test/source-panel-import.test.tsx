import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { AppMeta, ImportJob } from "@docurebuild/shared-types";

import { SourcePanel } from "@/components/workspace/source-panel";
import { i18n, initI18n } from "@/i18n";

const mocks = vi.hoisted(() => ({
  cancel: vi.fn(),
  start: vi.fn(),
  job: null as ImportJob | null,
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

const meta: AppMeta = {
  name: "DocuRebuild",
  version: "0.1.0",
  capabilities: {
    import_images: true,
    import_pdf: true,
    image_transform: true,
    element_extraction: true,
    ocr: false,
    ai: false,
    export: false,
  },
  max_import_mb: 200,
  max_upload_batch: 50,
  repository_url: null,
};

vi.mock("sonner", () => ({ toast: mocks.toast }));

vi.mock("@/hooks/use-app", () => ({
  useAppMeta: () => ({ data: meta }),
}));

vi.mock("@/hooks/use-projects", () => ({
  usePages: () => ({ data: [] }),
  useStartImport: () => ({ isPending: false, mutate: mocks.start, variables: undefined }),
  useCancelImportJob: () => ({ isPending: false, mutate: mocks.cancel }),
  useImportJobs: () => ({ data: [] }),
  useImportJob: () => ({ data: mocks.job }),
  useRotatePage: () => ({ isPending: false, mutate: vi.fn() }),
  useDeletePage: () => ({ isPending: false, mutate: vi.fn() }),
  useReorderPages: () => ({ isPending: false, mutate: vi.fn() }),
}));

vi.mock("@/components/workspace/ocr-dialog", () => ({ OcrDialog: () => null }));
vi.mock("@/components/workspace/edits-dialog", () => ({ EditsDialog: () => null }));
vi.mock("@/components/workspace/elements-dialog", () => ({ ElementsDialog: () => null }));
vi.mock("@/hooks/use-elements", () => ({
  useElements: () => ({ data: [] }),
  useCreateElement: () => ({ mutateAsync: vi.fn() }),
  useUpdateElement: () => ({ mutate: vi.fn() }),
  useDeleteElement: () => ({ mutate: vi.fn() }),
}));

function makeJob(overrides: Partial<ImportJob> = {}): ImportJob {
  return {
    id: "job-1",
    kind: "pages_import",
    status: "running",
    progress: 0.5,
    total_pages: 2,
    imported_pages: 1,
    current_file: "အခန်း-၃.pdf",
    file_count: 2,
    filenames: ["ဓာတ်ပုံ.png", "အခန်း-၃.pdf"],
    error: null,
    error_code: null,
    created_at: "2026-11-10T00:00:00Z",
    updated_at: "2026-11-10T00:00:01Z",
    completed_at: null,
    ...overrides,
  };
}

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <SourcePanel projectId="project-1" />
    </QueryClientProvider>,
  );
}

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

beforeEach(() => {
  mocks.job = null;
  mocks.cancel.mockReset();
  mocks.start.mockReset();
  mocks.toast.success.mockReset();
  mocks.toast.error.mockReset();
  mocks.toast.info.mockReset();
});

describe("SourcePanel import job feedback", () => {
  it("shows page progress, the current Burmese filename and a cancel action", () => {
    mocks.job = makeJob();
    renderPanel();

    const progressbar = screen.getByRole("progressbar");
    expect(progressbar).toHaveAttribute("aria-valuenow", "50");
    expect(screen.getByText("1 of 2 pages")).toBeInTheDocument();
    expect(screen.getByText("Importing…")).toBeInTheDocument();
    expect(screen.getByText("Current file: အခန်း-၃.pdf")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Cancel import/ })).toBeEnabled();
  });

  it("requests cancellation for the active job", () => {
    mocks.job = makeJob();
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: /Cancel import/ }));
    expect(mocks.cancel).toHaveBeenCalledWith("job-1", expect.anything());
  });

  it("disables cancellation while the job is stopping", () => {
    mocks.job = makeJob({ status: "cancelling" });
    renderPanel();

    expect(screen.getByText("Cancelling import…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Cancel import/ })).toBeDisabled();
  });

  it("reports a localized failure once the job settles", async () => {
    mocks.job = makeJob({
      status: "failed",
      progress: 0,
      imported_pages: 0,
      current_file: null,
      error: "PDF page 2 could not be rendered.",
      error_code: "pdf_page_render_failed",
      completed_at: "2026-11-10T00:00:02Z",
    });
    renderPanel();

    await waitFor(() =>
      expect(mocks.toast.error).toHaveBeenCalledWith(
        "One of the PDF pages could not be rendered.",
      ),
    );
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("reports a cancellation with the number of kept pages", async () => {
    mocks.job = makeJob({
      status: "cancelled",
      progress: 0.5,
      imported_pages: 1,
      current_file: null,
      completed_at: "2026-11-10T00:00:02Z",
    });
    renderPanel();

    await waitFor(() =>
      expect(mocks.toast.info).toHaveBeenCalledWith(
        "Import cancelled. 1 finished page was kept.",
      ),
    );
  });
});
