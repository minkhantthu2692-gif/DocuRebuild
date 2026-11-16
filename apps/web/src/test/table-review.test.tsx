import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type { TableProposalCandidate } from "@docurebuild/shared-types";

import { TableReview } from "@/components/workspace/table-review";
import { i18n, initI18n } from "@/i18n";

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

function proposal(): TableProposalCandidate {
  return {
    block_ids: ["a"],
    rows: 2,
    columns: 2,
    has_confidence: false,
    uncertain_cells: 0,
    empty_cells: 0,
    warnings: [],
    source: { x: 0, y: 100, width: 240, height: 80 },
    cells: [
      { row: 0, column: 0, text: "Name", confidence: null, uncertain: false, empty: false },
      { row: 0, column: 1, text: "Value", confidence: null, uncertain: false, empty: false },
      { row: 1, column: 0, text: "Mass", confidence: null, uncertain: false, empty: false },
      { row: 1, column: 1, text: "2", confidence: null, uncertain: false, empty: false },
    ],
  };
}

function renderReview(sourceImageUrl: string | null) {
  return render(
    <TableReview
      proposal={proposal()}
      sourceImageUrl={sourceImageUrl}
      pageWidth={1200}
      pageHeight={800}
      headerRow={false}
      onHeaderRowChange={vi.fn()}
      acknowledged
      onAcknowledgedChange={vi.fn()}
    />,
  );
}

describe("TableReview source comparison", () => {
  it("shows the source crop positioned from the proposal box", () => {
    const { container } = renderReview("http://api/pages/1/image");

    const image = container.querySelector("figure img");
    expect(image).not.toBeNull();
    expect(image).toHaveAttribute("src", "http://api/pages/1/image");
    // The page is 1200x800 and the crop is the 240x80 box at y=100 with the
    // preview's 10px padding, clamped to the top-left edge.
    expect(image).toHaveStyle({
      left: "0%",
      top: "-90%",
      width: "480%",
      height: "800%",
    });
  });

  it("toggles the crop without touching the grid", () => {
    const { container } = renderReview("http://api/pages/1/image");

    expect(screen.getByText("Name")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Hide source" }));

    expect(container.querySelector("figure img")).toBeNull();
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Compare with source" }),
    ).toBeInTheDocument();
  });

  it("hides the toggle when no page image is available", () => {
    renderReview(null);

    expect(
      screen.queryByRole("button", { name: "Compare with source" }),
    ).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Hide source" }),
    ).toBeNull();
  });
});
