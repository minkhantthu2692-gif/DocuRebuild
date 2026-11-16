import { describe, expect, it } from "vitest";

import type { TableProposalCandidate, TableProposalCell } from "@docurebuild/shared-types";

import { proposalRows, tableCandidatePreview } from "@/lib/table-candidates";

function cell(
  row: number,
  column: number,
  text: string,
  empty = false,
): TableProposalCell {
  return {
    row,
    column,
    text,
    confidence: null,
    uncertain: false,
    empty,
  };
}

function candidate(cells: TableProposalCell[]): TableProposalCandidate {
  return {
    block_ids: ["a"],
    rows: 2,
    columns: 2,
    has_confidence: false,
    uncertain_cells: 0,
    empty_cells: 0,
    warnings: [],
    cells,
  };
}

describe("proposalRows", () => {
  it("places cells at their coordinates and leaves missing cells empty", () => {
    expect(
      proposalRows({
        rows: 2,
        columns: 2,
        cells: [cell(0, 1, "B"), cell(1, 0, "C")],
      }),
    ).toEqual([
      ["", "B"],
      ["C", ""],
    ]);
  });

  it("ignores a cell outside the declared grid instead of growing it", () => {
    expect(
      proposalRows({
        rows: 1,
        columns: 1,
        cells: [cell(0, 0, "A"), cell(3, 4, "outside")],
      }),
    ).toEqual([["A"]]);
  });
});

describe("tableCandidatePreview", () => {
  it("joins the first row and skips empty cells", () => {
    expect(
      tableCandidatePreview(
        candidate([
          cell(0, 0, "Name"),
          cell(0, 1, "Value"),
          cell(0, 2, "", true),
          cell(1, 0, "Mass"),
        ]),
      ),
    ).toBe("Name · Value");
  });

  it("returns an empty string when the first row has no text", () => {
    expect(tableCandidatePreview(candidate([cell(0, 0, "", true)]))).toBe("");
  });
});
