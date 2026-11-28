import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  PageSummary,
  PageTableProposals,
  TableProposalCandidate,
} from "@docurebuild/shared-types";

import { PageTablesDialog } from "@/components/workspace/page-tables-dialog";
import { useWorkspaceActions } from "@/components/workspace/workspace-actions-context";
import { WorkspaceActionsProvider } from "@/components/workspace/workspace-actions";
import { i18n, initI18n } from "@/i18n";

const mocks = vi.hoisted(() => ({
  proposals: null as PageTableProposals | null,
}));

vi.mock("@/hooks/use-table-proposal", () => ({
  tableProposalKey: () => ["tables", "proposal"],
  pageTableProposalsKey: () => ["tables", "page"],
  useTableProposal: () => ({
    data: null,
    isLoading: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  }),
  usePageTableProposals: () => ({
    data: mocks.proposals,
    isLoading: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

beforeEach(() => {
  mocks.proposals = null;
  vi.restoreAllMocks();
});

function page(): PageSummary {
  return {
    id: "page-1",
    page_number: 4,
    source_kind: "pdf",
    status: "ready",
    width: 1200,
    height: 800,
    original_asset_id: "asset-page",
    display_asset_id: "asset-page",
    thumbnail_asset_id: "asset-thumb",
    original_filename: "nested.pdf",
    rotation: 0,
    pdf_page_number: 1,
    edits: { geometry: [], filters: {} as PageSummary["edits"]["filters"] },
    created_at: "2026-01-01T00:00:00+00:00",
    updated_at: "2026-01-01T00:00:00+00:00",
  };
}

function cells(
  texts: string[][],
  options: { empty?: boolean } = {},
): TableProposalCandidate["cells"] {
  const list: TableProposalCandidate["cells"] = [];
  texts.forEach((row, rowIndex) => {
    row.forEach((text, columnIndex) => {
      list.push({
        row: rowIndex,
        column: columnIndex,
        text,
        confidence: 92,
        uncertain: false,
        empty: options.empty === true && text === "",
        alignment: null,
      });
    });
  });
  return list;
}

function candidate(
  overrides: Partial<TableProposalCandidate> = {},
): TableProposalCandidate {
  return {
    key: "table-0-0-200-200",
    block_ids: ["block-1"],
    rows: 2,
    columns: 2,
    has_confidence: true,
    uncertain_cells: 0,
    empty_cells: 0,
    warnings: [],
    source: { x: 0, y: 0, width: 200, height: 200 },
    cells: cells([
      ["P1", "P2"],
      ["P3", "P4"],
    ]),
    nested: null,
    nested_count: 0,
    ...overrides,
  };
}

function proposals(): PageTableProposals {
  const parent = candidate({
    key: "table-0-0-200-200",
    cells: cells(
      [
        ["", "P2"],
        ["P3", "P4"],
      ],
      { empty: true },
    ),
    empty_cells: 1,
    warnings: ["empty_cells"],
    nested_count: 1,
  });
  const child = candidate({
    key: "table-20-20-80-80",
    source: { x: 20, y: 20, width: 80, height: 80 },
    cells: cells([
      ["C1", "C2"],
      ["C3", "C4"],
    ]),
    nested: {
      parent_key: parent.key,
      parent_row: 0,
      parent_column: 0,
    },
  });
  return {
    page_id: "page-1",
    run_id: "run-1",
    engine: "tesseract",
    page_width: 1200,
    page_height: 800,
    candidates: [parent, child],
  };
}

/** Exposes the pending insertion so the test can assert what would be written. */
function InsertionProbe() {
  const { insertion } = useWorkspaceActions();
  return <pre data-testid="insertion">{JSON.stringify(insertion)}</pre>;
}

function renderDialog() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <WorkspaceActionsProvider>
        <PageTablesDialog
          projectId="project-1"
          page={page()}
          open
          onOpenChange={vi.fn()}
        />
        <InsertionProbe />
      </WorkspaceActionsProvider>
    </QueryClientProvider>,
  );
}

function insertion() {
  return JSON.parse(screen.getByTestId("insertion").textContent ?? "null");
}

describe("page tables dialog nested candidates", () => {
  it("marks the parent and child with their nested relationship", () => {
    mocks.proposals = proposals();
    renderDialog();

    expect(screen.getByText("1 nested table(s)")).toBeInTheDocument();
    expect(screen.getByText("Nested in table 1")).toBeInTheDocument();
  });

  it("explains a nested child and records its parent cell in the note", () => {
    mocks.proposals = proposals();
    renderDialog();

    const childButton = screen.getByText("Nested in table 1").closest("button");
    expect(childButton).not.toBeNull();
    fireEvent.click(childButton as HTMLButtonElement);

    expect(
      screen.getByText(/inside cell \(row 1, column 1\) of table 1/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Insert table" }));

    const pending = insertion();
    expect(pending.note).toContain(
      "nested in table 1 cell (row 1, column 1)",
    );
    expect(pending.rows).toEqual([
      ["C1", "C2"],
      ["C3", "C4"],
    ]);
  });

  it("keeps the plain page note for a parent table", () => {
    mocks.proposals = proposals();
    renderDialog();

    const parentButton = screen.getByText("1 nested table(s)").closest("button");
    expect(parentButton).not.toBeNull();
    fireEvent.click(parentButton as HTMLButtonElement);

    fireEvent.click(screen.getByRole("button", { name: "Insert table" }));

    const pending = insertion();
    expect(pending.note).toBe(
      "Source: page 4 · detected table · review each cell",
    );
  });
});
