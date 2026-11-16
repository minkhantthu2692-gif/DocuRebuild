import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { TableProposalCandidate } from "@docurebuild/shared-types";

import { useTableDraft } from "@/hooks/use-table-draft";

function proposal(overrides: Partial<TableProposalCandidate> = {}): TableProposalCandidate {
  return {
    block_ids: ["a"],
    rows: 2,
    columns: 2,
    has_confidence: true,
    uncertain_cells: 0,
    empty_cells: 0,
    warnings: [],
    source: { x: 0, y: 0, width: 10, height: 10 },
    cells: [
      { row: 0, column: 0, text: "Name", confidence: 90, uncertain: false, empty: false },
      { row: 0, column: 1, text: "Value", confidence: 90, uncertain: false, empty: false },
      { row: 1, column: 0, text: "Mass", confidence: 90, uncertain: false, empty: false },
      { row: 1, column: 1, text: "2", confidence: 90, uncertain: false, empty: false },
    ],
    ...overrides,
  };
}

describe("useTableDraft", () => {
  it("mirrors the proposal until a cell is edited", () => {
    const { result } = renderHook(() => useTableDraft(proposal(), "a"));

    expect(result.current.rows).toEqual([
      ["Name", "Value"],
      ["Mass", "2"],
    ]);
    expect(result.current.changedCount).toBe(0);
    expect(result.current.edited.size).toBe(0);
  });

  it("applies an edit without changing the proposal", () => {
    const data = proposal();
    const { result } = renderHook(() => useTableDraft(data, "a"));

    act(() => result.current.setCell(1, 1, "4"));

    expect(result.current.rows[1][1]).toBe("4");
    expect(result.current.changedCount).toBe(1);
    expect(result.current.edited.has("1:1")).toBe(true);
    // The proposal itself is untouched, so the review still shows what the
    // engine read.
    expect(data.cells[3].text).toBe("2");
  });

  it("drops the change when the text matches the proposal again", () => {
    const { result } = renderHook(() => useTableDraft(proposal(), "a"));

    act(() => result.current.setCell(0, 0, "Element"));
    expect(result.current.changedCount).toBe(1);

    act(() => result.current.setCell(0, 0, "Name"));

    expect(result.current.changedCount).toBe(0);
    expect(result.current.edited.has("0:0")).toBe(false);
    expect(result.current.rows[0][0]).toBe("Name");
  });

  it("resets every edit", () => {
    const { result } = renderHook(() => useTableDraft(proposal(), "a"));

    act(() => result.current.setCell(0, 0, "Element"));
    act(() => result.current.setCell(1, 1, "4"));
    expect(result.current.changedCount).toBe(2);

    act(() => result.current.reset());

    expect(result.current.changedCount).toBe(0);
    expect(result.current.rows).toEqual([
      ["Name", "Value"],
      ["Mass", "2"],
    ]);
  });

  it("starts clean for a different proposal", () => {
    const first = proposal();
    const { result, rerender } = renderHook(
      ({ data, key }: { data: TableProposalCandidate; key: string }) =>
        useTableDraft(data, key),
      { initialProps: { data: first, key: "a" } },
    );

    act(() => result.current.setCell(0, 0, "Element"));
    expect(result.current.changedCount).toBe(1);

    const second = proposal({ block_ids: ["b"] });
    rerender({ data: second, key: "b" });

    expect(result.current.changedCount).toBe(0);
    expect(result.current.rows[0][0]).toBe("Name");
  });

  it("ignores a coordinate outside the grid", () => {
    const { result } = renderHook(() => useTableDraft(proposal(), "a"));

    act(() => result.current.setCell(9, 9, "outside"));

    expect(result.current.changedCount).toBe(0);
    expect(result.current.rows).toHaveLength(2);
  });

  it("handles a missing proposal", () => {
    const { result } = renderHook(() => useTableDraft(null, ""));

    expect(result.current.rows).toEqual([]);
    expect(result.current.changedCount).toBe(0);
    expect(() => act(() => result.current.setCell(0, 0, "x"))).not.toThrow();
  });
});
