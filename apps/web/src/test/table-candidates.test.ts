import { describe, expect, it } from "vitest";

import type {
  TableAlignment,
  TableProposalCandidate,
  TableProposalCell,
} from "@docurebuild/shared-types";

import {
  proposalAlignments,
  proposalRows,
  sourceCropGeometry,
  tableCandidatePreview,
} from "@/lib/table-candidates";

function cell(
  row: number,
  column: number,
  text: string,
  empty = false,
  alignment: TableAlignment | null = null,
): TableProposalCell {
  return {
    row,
    column,
    text,
    confidence: null,
    uncertain: false,
    empty,
    alignment,
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
    source: { x: 0, y: 0, width: 100, height: 100 },
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

describe("proposalAlignments", () => {
  it("places alignments at their coordinates and leaves missing cells null", () => {
    expect(
      proposalAlignments({
        rows: 2,
        columns: 2,
        cells: [cell(0, 0, "Name", false, "left"), cell(1, 1, "2", false, "right")],
      }),
    ).toEqual([
      ["left", null],
      [null, "right"],
    ]);
  });

  it("ignores a cell outside the declared grid", () => {
    expect(
      proposalAlignments({
        rows: 1,
        columns: 1,
        cells: [cell(0, 0, "A", false, "center"), cell(2, 2, "B", false, "right")],
      }),
    ).toEqual([["center"]]);
  });
});

describe("sourceCropGeometry", () => {
  it("maps the box onto the full page as percentages", () => {
    expect(
      sourceCropGeometry({ x: 0, y: 100, width: 240, height: 80 }, 1200, 800),
    ).toEqual({
      aspectRatio: 3,
      image: { left: 0, top: -125, width: 500, height: 1000 },
    });
  });

  it("clamps a box that runs past the page edge", () => {
    expect(
      sourceCropGeometry({ x: -20, y: 0, width: 1220, height: 800 }, 1200, 800),
    ).toEqual({
      aspectRatio: 1.5,
      image: { left: 0, top: 0, width: 100, height: 100 },
    });
  });

  it("returns null when the page size or box is unusable", () => {
    expect(sourceCropGeometry({ x: 0, y: 0, width: 10, height: 10 }, null, 800)).toBeNull();
    expect(sourceCropGeometry({ x: 0, y: 0, width: 0, height: 10 }, 1200, 800)).toBeNull();
    expect(sourceCropGeometry({ x: 1300, y: 0, width: 10, height: 10 }, 1200, 800)).toBeNull();
  });
});
