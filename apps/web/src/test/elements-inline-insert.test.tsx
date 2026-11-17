import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { ElementSummary, PageSummary } from "@docurebuild/shared-types";

import { ElementsDialog } from "@/components/workspace/elements-dialog";
import { useWorkspaceActions } from "@/components/workspace/workspace-actions-context";
import { WorkspaceActionsProvider } from "@/components/workspace/workspace-actions";
import { i18n, initI18n } from "@/i18n";
import { api } from "@/lib/api";

const mocks = vi.hoisted(() => ({
  elements: [] as ElementSummary[],
  createElement: vi.fn(),
}));

vi.mock("@/hooks/use-elements", () => ({
  useElements: () => ({
    data: mocks.elements,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useCreateElement: () => ({ mutateAsync: mocks.createElement, isPending: false }),
  useUpdateElement: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteElement: () => ({ mutate: vi.fn(), isPending: false }),
  useExtractElementText: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateElementText: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/hooks/use-ocr", () => ({
  useOcrCapabilities: () => ({ data: { available: false, languages: [] } }),
}));

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

beforeEach(() => {
  mocks.elements = [];
  mocks.createElement.mockReset();
  vi.restoreAllMocks();
});

const PAGE: PageSummary = {
  id: "page-1",
  page_number: 2,
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
    kind: "figure",
    asset_id: "asset-1",
    x: 10,
    y: 20,
    width: 120,
    height: 60,
    caption: "Wave function",
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

/** Exposes the pending insertion so the test can assert what would be written. */
function InsertionProbe() {
  const { insertion } = useWorkspaceActions();
  return <pre data-testid="insertion">{JSON.stringify(insertion)}</pre>;
}

function renderDialog(
  options: { pendingSelection?: { x: number; y: number; width: number; height: number } } = {},
) {
  const onInserted = vi.fn();
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <WorkspaceActionsProvider>
        <ElementsDialog
          projectId="project-1"
          page={PAGE}
          open
          onOpenChange={vi.fn()}
          pendingSelection={options.pendingSelection ?? null}
          onPendingConsumed={vi.fn()}
          pendingProposal={null}
          onProposalConsumed={vi.fn()}
          onRequestSelection={vi.fn()}
          onInserted={onInserted}
        />
        <InsertionProbe />
      </WorkspaceActionsProvider>
    </QueryClientProvider>,
  );
  return onInserted;
}

function insertion() {
  return JSON.parse(screen.getByTestId("insertion").textContent ?? "null");
}

describe("elements dialog insertion placement", () => {
  it("inserts a saved region inline as a single image node", async () => {
    mocks.elements = [element()];
    const onInserted = renderDialog();

    fireEvent.click(
      screen.getByRole("button", { name: "Insert inline" }),
    );

    expect(insertion()).toMatchObject({
      type: "inlineImage",
      src: api.assetUrl("project-1", "asset-1", element().updated_at),
      alt: "Wave function",
    });
    expect(onInserted).toHaveBeenCalledTimes(1);
  });

  it("keeps the block insertion unchanged when no placement is chosen", async () => {
    mocks.elements = [element()];
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Insert" }));

    const pending = insertion();
    expect(pending.type).toBe("figure");
    expect(pending.caption).toBe("Wave function");
    expect(pending.note).toContain("page 2");
    expect(pending.note).toContain("Unverified");
  });

  it("saves and inserts a new region inline when inline placement is chosen", async () => {
    mocks.createElement.mockResolvedValue(
      element({ id: "element-9", asset_id: "asset-9", caption: "Cropped plot" }),
    );
    renderDialog({ pendingSelection: { x: 10, y: 20, width: 120, height: 60 } });

    fireEvent.click(screen.getByRole("radio", { name: "Inline image" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Save and insert" }),
    );

    await waitFor(() => expect(insertion()).not.toBeNull());
    expect(mocks.createElement).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "figure", x: 10, y: 20, width: 120, height: 60 }),
    );
    expect(insertion()).toMatchObject({
      type: "inlineImage",
      src: api.assetUrl("project-1", "asset-9", element().updated_at),
      alt: "Cropped plot",
    });
  });

  it("still saves and inserts a block figure by default", async () => {
    mocks.createElement.mockResolvedValue(element({ id: "element-9" }));
    renderDialog({ pendingSelection: { x: 10, y: 20, width: 120, height: 60 } });

    fireEvent.click(
      screen.getByRole("button", { name: "Save and insert" }),
    );

    await waitFor(() => expect(insertion()).not.toBeNull());
    expect(insertion().type).toBe("figure");
    expect(insertion().caption).toBe("Wave function");
  });

  it("hides the source-note option for an inline image", async () => {
    renderDialog();
    expect(screen.getByLabelText("Add a source note to the document")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Inline image" }));

    expect(
      screen.queryByLabelText("Add a source note to the document"),
    ).not.toBeInTheDocument();
  });
});
