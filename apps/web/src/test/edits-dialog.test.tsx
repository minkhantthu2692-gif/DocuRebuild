import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { PageEdits, PageSummary } from "@docurebuild/shared-types";

import { EditsDialog } from "@/components/workspace/edits-dialog";
import { i18n, initI18n } from "@/i18n";

const mocks = vi.hoisted(() => ({
  updateEdits: vi.fn(),
  resetEdits: vi.fn(),
  estimateSkew: vi.fn(),
}));

vi.mock("@/hooks/use-projects", () => ({
  useUpdatePageEdits: () => ({
    mutateAsync: mocks.updateEdits,
    isPending: false,
  }),
  useResetPageEdits: () => ({
    mutateAsync: mocks.resetEdits,
    isPending: false,
  }),
  useEstimatePageSkew: () => ({
    mutateAsync: mocks.estimateSkew,
    isPending: false,
  }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    assetUrl: (projectId: string, assetId: string | null, version?: string) =>
      assetId ? `http://test/${projectId}/${assetId}?v=${version ?? ""}` : null,
    pageBasePreview: (projectId: string, pageId: string) =>
      `http://test/${projectId}/${pageId}/base`,
  },
}));

const DEFAULT_EDITS: PageEdits = {
  geometry: [],
  filters: {
    grayscale: false,
    contrast: 1,
    brightness: 1,
    sharpness: 1,
    denoise: 0,
    shadow_removal: false,
    background_cleanup: false,
    threshold: false,
    threshold_level: 55,
  },
};

function makePage(overrides: Partial<PageSummary> = {}): PageSummary {
  return {
    id: "page-1",
    page_number: 1,
    source_kind: "image",
    status: "ready",
    width: 1200,
    height: 1600,
    original_asset_id: "original-1",
    display_asset_id: "display-1",
    thumbnail_asset_id: "thumb-1",
    original_filename: "scan.png",
    rotation: 0,
    pdf_page_number: null,
    edits: DEFAULT_EDITS,
    created_at: "2026-01-01T00:00:00+00:00",
    updated_at: "2026-01-01T00:00:00+00:00",
    ...overrides,
  };
}

function renderDialog(page: PageSummary = makePage()) {
  const onOpenChange = vi.fn();
  const result = render(
    <EditsDialog
      projectId="project-1"
      page={page}
      open
      onOpenChange={onOpenChange}
    />,
  );
  return { ...result, onOpenChange };
}

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

beforeEach(() => {
  mocks.updateEdits.mockReset();
  mocks.resetEdits.mockReset();
  mocks.estimateSkew.mockReset();
  mocks.updateEdits.mockImplementation(async ({ pageId, edits }: { pageId: string; edits: PageEdits }) =>
    makePage({ id: pageId, edits, updated_at: "2026-01-01T00:00:01+00:00" }),
  );
});

describe("edit image dialog", () => {
  it("keeps the dialog and preview mounted while a filter is toggled", async () => {
    const page = makePage();
    const { rerender } = renderDialog(page);

    const preview = screen.getByRole("img");
    fireEvent.click(screen.getByRole("switch", { name: "Grayscale" }));

    expect(screen.getByRole("switch", { name: "Grayscale" })).toBeChecked();
    expect(screen.getByRole("img")).toBe(preview);

    // A commit updates the pages cache, which hands the dialog a new page
    // object with the same id. That must not reset the open dialog.
    rerender(
      <EditsDialog
        projectId="project-1"
        page={makePage({
          edits: { ...DEFAULT_EDITS, filters: { ...DEFAULT_EDITS.filters, grayscale: true } },
          updated_at: "2026-01-01T00:00:01+00:00",
        })}
        open
        onOpenChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("switch", { name: "Grayscale" })).toBeChecked();
    expect(screen.getByRole("img")).toBe(preview);

    await waitFor(() => expect(mocks.updateEdits).toHaveBeenCalledTimes(1), {
      timeout: 2000,
    });
    expect(mocks.updateEdits.mock.calls[0][0].edits.filters.grayscale).toBe(true);
    // The refreshed source is painted on the same element instead of
    // remounting it.
    expect(screen.getByRole("img")).toBe(preview);
  });

  it("coalesces rapid filter changes into one commit", async () => {
    renderDialog();
    const toggle = screen.getByRole("switch", { name: "Grayscale" });

    fireEvent.click(toggle);
    fireEvent.click(toggle);

    expect(toggle).not.toBeChecked();
    await waitFor(() => expect(mocks.updateEdits).toHaveBeenCalledTimes(1), {
      timeout: 2000,
    });
    expect(mocks.updateEdits.mock.calls[0][0].edits.filters.grayscale).toBe(false);
  });

  it("switches to the original without remounting the image", () => {
    renderDialog(
      makePage({
        edits: {
          ...DEFAULT_EDITS,
          filters: { ...DEFAULT_EDITS.filters, grayscale: true },
        },
      }),
    );

    const preview = screen.getByRole("img");
    fireEvent.click(screen.getByRole("button", { name: "Compare with original" }));

    expect(screen.getByRole("img")).toBe(preview);
    expect(screen.getByRole("button", { name: "Back to adjusted view" })).toBeInTheDocument();
  });
});
