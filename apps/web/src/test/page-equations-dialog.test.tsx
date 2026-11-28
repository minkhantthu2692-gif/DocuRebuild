import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ElementSummary,
  PageEquationProposals,
  PageSummary,
} from "@docurebuild/shared-types";

import { PageEquationsDialog } from "@/components/workspace/page-equations-dialog";
import { i18n, initI18n } from "@/i18n";

const mocks = vi.hoisted(() => ({
  proposals: null as PageEquationProposals | null,
  createElement: vi.fn(),
}));

vi.mock("@/hooks/use-equation-proposals", () => ({
  usePageEquationProposals: () => ({
    data: mocks.proposals,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

vi.mock("@/hooks/use-elements", () => ({
  useCreateElement: () => ({ mutateAsync: mocks.createElement, isPending: false }),
}));

vi.mock("@/hooks/use-api-error", () => ({
  useApiErrorMessage: () => (error: unknown) => String(error),
}));

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

beforeEach(() => {
  mocks.proposals = null;
  mocks.createElement.mockReset();
});

const PAGE: PageSummary = {
  id: "page-1",
  page_number: 3,
  source_kind: "image",
  status: "ready",
  width: 800,
  height: 600,
  original_asset_id: "page-asset",
  display_asset_id: "page-asset",
  thumbnail_asset_id: null,
  original_filename: "scan.png",
  rotation: 0,
  pdf_page_number: null,
  edits: {
    geometry: [],
    filters: {
      grayscale: false,
      contrast: 1.0,
      brightness: 1.0,
      sharpness: 1.0,
      denoise: 0,
      shadow_removal: false,
      background_cleanup: false,
      threshold: false,
      threshold_level: 55,
    },
  },
  created_at: "2026-01-01T00:00:00+00:00",
  updated_at: "2026-01-01T00:00:00+00:00",
};

function element(overrides: Partial<ElementSummary> = {}): ElementSummary {
  return {
    id: "element-1",
    page_id: "page-1",
    kind: "equation",
    asset_id: "asset-1",
    x: 100,
    y: 200,
    width: 320,
    height: 40,
    caption: "",
    source: "manual",
    verified: false,
    text: "",
    text_confidence: null,
    text_engine: null,
    text_engine_version: null,
    text_languages: [],
    text_corrected: false,
    text_updated_at: null,
    stale: false,
    created_at: "2026-01-01T00:00:00+00:00",
    updated_at: "2026-01-01T00:00:00+00:00",
    ...overrides,
  };
}

function readyProposals(): PageEquationProposals {
  return {
    status: "ready",
    page_id: "page-1",
    page_width: 800,
    page_height: 600,
    ocr_run_id: "run-1",
    engine: "tesseract",
    proposals: [
      {
        key: "equation-90-194-340-52",
        x: 90,
        y: 194,
        width: 340,
        height: 52,
        text: "E = mc^2",
        display: true,
        confidence: "high",
        reason: "equation_text",
        block_ids: ["block-1"],
        reading_index: 0,
      },
    ],
  };
}

function renderDialog(onReview = vi.fn()) {
  render(
    <PageEquationsDialog
      projectId="project-1"
      page={PAGE}
      open
      onOpenChange={vi.fn()}
      onReview={onReview}
    />,
  );
  return { onReview };
}

describe("PageEquationsDialog", () => {
  it("turns a chosen candidate into a crop and hands it to the equation review", async () => {
    mocks.proposals = readyProposals();
    const created = element();
    mocks.createElement.mockResolvedValue(created);
    const { onReview } = renderDialog();

    fireEvent.click(screen.getByText("Equation 1"));

    await waitFor(() => {
      expect(mocks.createElement).toHaveBeenCalledWith({
        kind: "equation",
        x: 90,
        y: 194,
        width: 340,
        height: 52,
        caption: "",
      });
    });
    await waitFor(() => {
      expect(onReview).toHaveBeenCalledWith(created, "E = mc^2");
    });
  });

  it("shows the OCR state instead of candidates when the layout is stale", () => {
    mocks.proposals = {
      status: "ocr_stale",
      page_id: "page-1",
      page_width: 800,
      page_height: 600,
      ocr_run_id: "run-1",
      engine: "tesseract",
      proposals: [],
    };
    renderDialog();

    expect(screen.getByText("Equations are not available yet")).toBeTruthy();
    expect(screen.getByText(/Re-run OCR to refresh/)).toBeTruthy();
    expect(mocks.createElement).not.toHaveBeenCalled();
  });

  it("shows an empty state when no equation block exists", () => {
    mocks.proposals = {
      ...readyProposals(),
      proposals: [],
    };
    renderDialog();

    expect(screen.getByText("No equations detected")).toBeTruthy();
  });
});
