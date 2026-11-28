import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { beforeAll, describe, expect, it } from "vitest";

import type { TableProposalCandidate } from "@docurebuild/shared-types";

import { TableReview } from "@/components/workspace/table-review";
import { useTableDraft } from "@/hooks/use-table-draft";
import { i18n, initI18n } from "@/i18n";

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

function proposal(): TableProposalCandidate {
  return {
    key: "table-0-100-240-80",
    block_ids: ["a"],
    rows: 2,
    columns: 2,
    has_confidence: false,
    uncertain_cells: 0,
    empty_cells: 0,
    warnings: [],
    source: { x: 0, y: 100, width: 240, height: 80 },
    cells: [
      {
        row: 0,
        column: 0,
        text: "Name",
        confidence: null,
        uncertain: false,
        empty: false,
        alignment: "left",
      },
      {
        row: 0,
        column: 1,
        text: "Value",
        confidence: null,
        uncertain: false,
        empty: false,
        alignment: "center",
      },
      {
        row: 1,
        column: 0,
        text: "Mass",
        confidence: null,
        uncertain: false,
        empty: false,
        alignment: "left",
      },
      {
        row: 1,
        column: 1,
        text: "2",
        confidence: null,
        uncertain: false,
        empty: false,
        alignment: "right",
      },
    ],
  };
}

/**
 * TableReview expects the draft its dialog created, so the test renders the
 * same composition and exposes the rows that would be inserted.
 */
function ReviewHarness({
  sourceImageUrl,
  data = proposal(),
}: {
  sourceImageUrl: string | null;
  data?: TableProposalCandidate;
}) {
  const [headerRow, setHeaderRow] = useState(false);
  const [acknowledged, setAcknowledged] = useState(true);
  const draft = useTableDraft(data, "test");
  return (
    <>
      <TableReview
        proposal={data}
        draft={draft}
        sourceImageUrl={sourceImageUrl}
        pageWidth={1200}
        pageHeight={800}
        headerRow={headerRow}
        onHeaderRowChange={setHeaderRow}
        acknowledged={acknowledged}
        onAcknowledgedChange={setAcknowledged}
      />
      <output data-testid="rows">{JSON.stringify(draft.rows)}</output>
    </>
  );
}

function renderReview(sourceImageUrl: string | null = null, data?: TableProposalCandidate) {
  return render(<ReviewHarness sourceImageUrl={sourceImageUrl} data={data} />);
}

function mergedProposal(): TableProposalCandidate {
  return {
    key: "table-0-100-300-120",
    block_ids: ["a"],
    rows: 3,
    columns: 3,
    has_confidence: false,
    uncertain_cells: 0,
    empty_cells: 0,
    warnings: [],
    source: { x: 0, y: 100, width: 300, height: 120 },
    cells: [
      {
        row: 0,
        column: 0,
        text: "Merged header",
        confidence: null,
        uncertain: false,
        empty: false,
        alignment: null,
        colspan: 3,
      },
      {
        row: 1,
        column: 0,
        text: "Group",
        confidence: null,
        uncertain: false,
        empty: false,
        alignment: "left",
        rowspan: 2,
      },
      {
        row: 1,
        column: 1,
        text: "1.2",
        confidence: null,
        uncertain: false,
        empty: false,
        alignment: null,
      },
      {
        row: 1,
        column: 2,
        text: "3.4",
        confidence: null,
        uncertain: false,
        empty: false,
        alignment: null,
      },
      {
        row: 2,
        column: 1,
        text: "5.6",
        confidence: null,
        uncertain: false,
        empty: false,
        alignment: null,
      },
      {
        row: 2,
        column: 2,
        text: "7.8",
        confidence: null,
        uncertain: false,
        empty: false,
        alignment: null,
      },
    ],
  };
}

describe("TableReview merged cells", () => {
  it("renders spans and skips the coordinates another cell covers", () => {
    const { container } = renderReview(null, mergedProposal());

    const rows = container.querySelectorAll("tbody tr");
    expect(rows).toHaveLength(3);
    expect(rows[0]?.querySelectorAll("td")).toHaveLength(1);
    expect(screen.getByText("Merged header").closest("td")).toHaveAttribute(
      "colspan",
      "3",
    );
    expect(rows[1]?.querySelectorAll("td")).toHaveLength(3);
    expect(screen.getByText("Group").closest("td")).toHaveAttribute("rowspan", "2");
    // The covered coordinate under "Group" is not a cell of its own.
    expect(rows[2]?.querySelectorAll("td")).toHaveLength(2);
    expect(screen.getAllByText("Group")).toHaveLength(1);

    expect(screen.getByText("2 merged cell(s)")).toBeInTheDocument();
  });

  it("keeps the merged coordinates empty in the inserted rows", () => {
    renderReview(null, mergedProposal());

    expect(screen.getByTestId("rows").textContent).toBe(
      JSON.stringify([
        ["Merged header", "", ""],
        ["Group", "1.2", "3.4"],
        ["", "5.6", "7.8"],
      ]),
    );
  });
});

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
    renderReview();

    expect(
      screen.queryByRole("button", { name: "Compare with source" }),
    ).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Hide source" }),
    ).toBeNull();
  });
});

describe("TableReview alignment", () => {
  it("applies the detected alignment to cell text", () => {
    renderReview();

    expect(screen.getByText("Value")).toHaveStyle({ textAlign: "center" });
    expect(screen.getByText("2")).toHaveStyle({ textAlign: "right" });
    expect(screen.getByText("Mass")).toHaveStyle({ textAlign: "left" });
  });

  it("keeps the alignment while a cell is edited", () => {
    renderReview();
    fireEvent.click(screen.getByRole("button", { name: "Edit cells" }));

    expect(
      screen.getByRole("textbox", { name: "Cell row 1, column 2" }),
    ).toHaveStyle({ textAlign: "center" });
  });
});

describe("TableReview cell editing", () => {
  it("turns cells into labelled fields and applies edits to the inserted rows", () => {
    renderReview();

    expect(screen.queryByRole("textbox")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Edit cells" }));

    const first = screen.getByRole("textbox", { name: "Cell row 1, column 1" });
    expect(first).toHaveValue("Name");

    fireEvent.change(first, { target: { value: "Element" } });

    expect(screen.getByTestId("rows").textContent).toContain('"Element"');
    expect(screen.getByTestId("rows").textContent).not.toContain('"Name"');
    expect(screen.getByText("1 cell(s) edited")).toBeInTheDocument();
  });

  it("shows an empty field for a coordinate the proposal does not include", () => {
    const sparse = proposal();
    sparse.cells = sparse.cells.filter(
      (cell) => !(cell.row === 1 && cell.column === 1),
    );
    renderReview(null, sparse);
    fireEvent.click(screen.getByRole("button", { name: "Edit cells" }));

    // A missing coordinate stays empty; it is never folded into a neighbour.
    expect(
      screen.getByRole("textbox", { name: "Cell row 1, column 1" }),
    ).toHaveValue("Name");
    expect(
      screen.getByRole("textbox", { name: "Cell row 2, column 2" }),
    ).toHaveValue("");
  });

  it("clears an edit when the text matches the proposal again", () => {
    renderReview();
    fireEvent.click(screen.getByRole("button", { name: "Edit cells" }));
    const first = screen.getByRole("textbox", { name: "Cell row 1, column 1" });

    fireEvent.change(first, { target: { value: "Element" } });
    fireEvent.change(first, { target: { value: "Name" } });

    expect(screen.queryByText("1 cell(s) edited")).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Reset edits" }),
    ).toBeNull();
  });

  it("resets every edit from the toolbar", () => {
    renderReview();
    fireEvent.click(screen.getByRole("button", { name: "Edit cells" }));

    fireEvent.change(
      screen.getByRole("textbox", { name: "Cell row 1, column 1" }),
      { target: { value: "Element" } },
    );
    fireEvent.change(
      screen.getByRole("textbox", { name: "Cell row 2, column 2" }),
      { target: { value: "4" } },
    );
    expect(screen.getByText("2 cell(s) edited")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reset edits" }));

    expect(screen.queryByText("2 cell(s) edited")).toBeNull();
    expect(
      screen.getByRole("textbox", { name: "Cell row 1, column 1" }),
    ).toHaveValue("Name");
    expect(
      screen.getByRole("textbox", { name: "Cell row 2, column 2" }),
    ).toHaveValue("2");
  });

  it("hides the fields but keeps edits when editing finishes", () => {
    renderReview();
    fireEvent.click(screen.getByRole("button", { name: "Edit cells" }));
    fireEvent.change(
      screen.getByRole("textbox", { name: "Cell row 1, column 1" }),
      { target: { value: "Element" } },
    );

    fireEvent.click(screen.getByRole("button", { name: "Finish editing" }));

    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByText("Element")).toBeInTheDocument();
    expect(screen.getByText("1 cell(s) edited")).toBeInTheDocument();
  });

  it("keeps the proposal badges while a cell is edited", () => {
    renderReview();
    fireEvent.click(screen.getByRole("button", { name: "Edit cells" }));
    fireEvent.change(
      screen.getByRole("textbox", { name: "Cell row 1, column 1" }),
      { target: { value: "Element" } },
    );

    // The badges still describe the extracted proposal, not the draft, so an
    // edit cannot quietly look like text the engine produced.
    expect(screen.getByText("2 rows × 2 columns")).toBeInTheDocument();
  });
});
