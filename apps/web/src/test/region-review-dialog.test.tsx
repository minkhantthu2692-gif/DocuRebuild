import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProjectRegionProposals } from "@docurebuild/shared-types";

import { RegionReviewDialog } from "@/components/workspace/region-review-dialog";
import { i18n, initI18n } from "@/i18n";

const mocks = vi.hoisted(() => ({
  proposals: null as ProjectRegionProposals | null,
}));

vi.mock("@/hooks/use-elements", () => ({
  useProjectRegionProposals: () => ({
    data: mocks.proposals,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
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
});

function aggregate(): ProjectRegionProposals {
  return {
    pages: [
      {
        page_id: "page-1",
        page_number: 1,
        status: "ready",
        page_width: 800,
        page_height: 600,
        ocr_run_id: "run-1",
        engine: "tesseract",
        proposal_count: 1,
        proposals: [
          {
            key: "figure-1",
            kind: "figure",
            x: 40,
            y: 60,
            width: 300,
            height: 200,
            caption: "Figure one",
            confidence: "high",
            reason: "pdf_image_region",
            block_ids: [],
          },
        ],
      },
      {
        page_id: "page-2",
        page_number: 2,
        status: "ready",
        page_width: 800,
        page_height: 600,
        ocr_run_id: "run-2",
        engine: "tesseract",
        proposal_count: 2,
        proposals: [
          {
            key: "table-2",
            kind: "table",
            x: 40,
            y: 60,
            width: 300,
            height: 200,
            caption: "Table two",
            confidence: "medium",
            reason: "table_text_grid",
            block_ids: [],
          },
          {
            key: "equation-2",
            kind: "equation",
            x: 40,
            y: 300,
            width: 300,
            height: 40,
            caption: "",
            confidence: "low",
            reason: "equation_text",
            block_ids: [],
          },
        ],
      },
    ],
    total_proposals: 3,
    pages_with_proposals: 2,
    truncated: false,
    next_page_number: null,
  };
}

function renderDialog() {
  const onOpenPage = vi.fn();
  const onReviewProposal = vi.fn();
  render(
    <RegionReviewDialog
      projectId="project-1"
      open
      onOpenChange={vi.fn()}
      onOpenPage={onOpenPage}
      onReviewProposal={onReviewProposal}
    />,
  );
  return { onOpenPage, onReviewProposal };
}

describe("RegionReviewDialog", () => {
  it("lists pages in order and hands a chosen suggestion to the review flow", () => {
    mocks.proposals = aggregate();
    const { onReviewProposal, onOpenPage } = renderDialog();

    expect(screen.getByText("Page 1")).toBeTruthy();
    expect(screen.getByText("Page 2")).toBeTruthy();
    expect(screen.getByText("3 suggestions on 2 page(s)")).toBeTruthy();

    fireEvent.click(screen.getByText("Table two"));
    expect(onReviewProposal).toHaveBeenCalledWith(
      "page-2",
      expect.objectContaining({ key: "table-2", kind: "table" }),
    );

    fireEvent.click(screen.getAllByText("Open page")[1]);
    expect(onOpenPage).toHaveBeenCalledWith("page-2");
  });

  it("does not offer a save action of its own", () => {
    mocks.proposals = aggregate();
    renderDialog();

    expect(screen.queryByText("Save region")).toBeNull();
    expect(screen.queryByText("Save and insert")).toBeNull();
  });

  it("shows an empty state when no page has proposals", () => {
    mocks.proposals = {
      pages: [],
      total_proposals: 0,
      pages_with_proposals: 0,
      truncated: false,
      next_page_number: null,
    };
    renderDialog();

    expect(screen.getByText("No region suggestions yet")).toBeTruthy();
  });

  it("explains where to continue when the scan window is truncated", () => {
    mocks.proposals = {
      ...aggregate(),
      truncated: true,
      next_page_number: 3,
    };
    renderDialog();

    expect(screen.getByText(/Continue from page 3/)).toBeTruthy();
  });
});

