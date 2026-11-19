import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  AiTableResponse,
  ElementSummary,
  PageSummary,
} from "@docurebuild/shared-types";

import { AiTableDialog } from "@/components/workspace/ai-table-dialog";
import { useWorkspaceActions } from "@/components/workspace/workspace-actions-context";
import { WorkspaceActionsProvider } from "@/components/workspace/workspace-actions";
import { i18n, initI18n } from "@/i18n";
import { api } from "@/lib/api";

const mocks = vi.hoisted(() => ({
  visionModel: "llava:7b",
  visionBaseUrl: "",
  visionCostClass: "local" as "local" | "free" | "paid",
}));

vi.mock("@/hooks/use-ai", () => ({
  useAiTasks: () => ({
    data: {
      tasks: {
        table_structure: {
          configured: mocks.visionModel.length > 0,
          connection_id: mocks.visionModel ? "conn-1" : null,
          connection_name: mocks.visionModel ? "Local server" : null,
          base_url: mocks.visionBaseUrl || null,
          model_id: mocks.visionModel || null,
          model_display_name: mocks.visionModel || null,
          cost_class: mocks.visionModel ? mocks.visionCostClass : null,
          warnings: [],
        },
      },
    },
    isLoading: false,
  }),
}));

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

beforeEach(() => {
  mocks.visionModel = "llava:7b";
  mocks.visionBaseUrl = "";
  mocks.visionCostClass = "local";
  vi.restoreAllMocks();
});

function element(): ElementSummary {
  return {
    id: "element-1",
    page_id: "page-1",
    kind: "table",
    asset_id: "asset-1",
    x: 40,
    y: 120,
    width: 300,
    height: 90,
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
  };
}

function page(): PageSummary {
  return {
    id: "page-1",
    page_number: 4,
    source_kind: "image",
    status: "ready",
    width: 1200,
    height: 800,
    original_asset_id: "asset-page",
    display_asset_id: "asset-page",
    thumbnail_asset_id: "asset-thumb",
    original_filename: "page.png",
    rotation: 0,
    pdf_page_number: null,
    edits: { geometry: [], filters: {} as PageSummary["edits"]["filters"] },
    created_at: "2026-01-01T00:00:00+00:00",
    updated_at: "2026-01-01T00:00:00+00:00",
  };
}

function proposal(): AiTableResponse {
  return {
    element_id: "element-1",
    page_id: "page-1",
    provider: "ollama",
    model: "llava:7b",
    base_url: "http://127.0.0.1:11434",
    page_width: 1200,
    page_height: 800,
    rows: 2,
    columns: 2,
    uncertain_cells: 0,
    empty_cells: 0,
    warnings: ["no_confidence"],
    source: { x: 40, y: 120, width: 300, height: 90 },
    cells: [
      { row: 0, column: 0, text: "Item", confidence: null, uncertain: false, empty: false, alignment: null },
      { row: 0, column: 1, text: "Qty", confidence: null, uncertain: false, empty: false, alignment: null },
      { row: 1, column: 0, text: "Apples", confidence: null, uncertain: false, empty: false, alignment: null },
      { row: 1, column: 1, text: "3", confidence: null, uncertain: false, empty: false, alignment: null },
    ],
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
        <AiTableDialog
          projectId="project-1"
          element={element()}
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

describe("AI table dialog", () => {
  it("cannot read without a configured vision model", () => {
    mocks.visionModel = "";
    renderDialog();

    expect(
      screen.getByRole("button", { name: "Read table with AI" }),
    ).toBeDisabled();
    expect(
      screen.getByText(/Choose a vision model in Settings/),
    ).toBeInTheDocument();
  });

  it("requires acknowledgement before the read grid can be inserted", async () => {
    const read = vi
      .spyOn(api, "createAiTableProposal")
      .mockResolvedValue(proposal());
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Read table with AI" }));

    await waitFor(() => expect(screen.getByText("Item")).toBeInTheDocument());
    expect(read).toHaveBeenCalledWith("project-1", "element-1", {
      confirm_paid: true,
    });
    expect(screen.getByText("2 rows × 2 columns")).toBeInTheDocument();
    expect(screen.getByText(/Proposed by llava:7b/)).toBeInTheDocument();

    const insert = screen.getByRole("button", { name: "Insert table" });
    expect(insert).toBeDisabled();

    fireEvent.click(
      screen.getByLabelText(
        "I reviewed the flagged cells against the source page",
      ),
    );
    expect(insert).toBeEnabled();
    fireEvent.click(insert);

    const pending = insertion();
    expect(pending).toMatchObject({ type: "table", headerRow: false });
    expect(pending.rows).toEqual([
      ["Item", "Qty"],
      ["Apples", "3"],
    ]);
    expect(pending.note).toContain("page 4");
    expect(pending.note).toContain("proposed by llava:7b");
    expect(pending.note).not.toContain("manual cell corrections");
  });

  it("inserts corrected cells and says the model reply was corrected", async () => {
    vi.spyOn(api, "createAiTableProposal").mockResolvedValue(proposal());
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Read table with AI" }));
    await waitFor(() => expect(screen.getByText("Item")).toBeInTheDocument());
    fireEvent.click(
      screen.getByLabelText(
        "I reviewed the flagged cells against the source page",
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit cells" }));
    fireEvent.change(screen.getByLabelText("Cell row 2, column 1"), {
      target: { value: "Apricots" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Insert table" }));

    const pending = insertion();
    expect(pending.rows[1]).toEqual(["Apricots", "3"]);
    expect(pending.note).toContain("manual cell corrections");
  });

  it("drops earlier cell corrections when the table is read again", async () => {
    vi.spyOn(api, "createAiTableProposal").mockResolvedValue(proposal());
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Read table with AI" }));
    await waitFor(() => expect(screen.getByText("Item")).toBeInTheDocument());
    fireEvent.click(
      screen.getByLabelText(
        "I reviewed the flagged cells against the source page",
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "Edit cells" }));
    fireEvent.change(screen.getByLabelText("Cell row 2, column 1"), {
      target: { value: "Apricots" },
    });
    expect(screen.getByLabelText("Cell row 2, column 1")).toHaveValue(
      "Apricots",
    );

    // A second read replaces the grid; the old edit must not be re-applied at
    // the same coordinate.
    fireEvent.click(screen.getByRole("button", { name: "Read table with AI" }));
    await waitFor(() =>
      expect(screen.getByLabelText("Cell row 2, column 1")).toHaveValue(
        "Apples",
      ),
    );
  });

  it("asks before sending a paid read", async () => {
    mocks.visionBaseUrl = "https://api.example.com/v1";
    mocks.visionCostClass = "paid";
    const read = vi
      .spyOn(api, "createAiTableProposal")
      .mockResolvedValue(proposal());
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Read table with AI" }));

    const confirm = await screen.findByRole("button", {
      name: "Send paid request",
    });
    expect(read).not.toHaveBeenCalled();

    fireEvent.click(confirm);
    await waitFor(() =>
      expect(read).toHaveBeenCalledWith("project-1", "element-1", {
        confirm_paid: true,
      }),
    );
  });
});
