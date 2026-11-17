import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { ElementSummary } from "@docurebuild/shared-types";

import { RegionFormulaDialog } from "@/components/workspace/region-formula-dialog";
import { useWorkspaceActions } from "@/components/workspace/workspace-actions-context";
import { WorkspaceActionsProvider } from "@/components/workspace/workspace-actions";
import { i18n, initI18n } from "@/i18n";
import { api } from "@/lib/api";

const mocks = vi.hoisted(() => ({
  visionModel: "llava:7b",
}));

vi.mock("@/hooks/use-app", () => ({
  useAppSettings: () => ({
    data: { ai: { vision: { model: mocks.visionModel } } },
    isLoading: false,
  }),
}));

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

beforeEach(() => {
  mocks.visionModel = "llava:7b";
  vi.restoreAllMocks();
});

function element(text = "E = mc^2"): ElementSummary {
  return {
    id: "element-1",
    page_id: "page-1",
    kind: "equation",
    asset_id: "asset-1",
    x: 40,
    y: 120,
    width: 300,
    height: 90,
    caption: "",
    source: "manual",
    verified: false,
    text,
    text_confidence: 82,
    text_engine: "tesseract",
    text_engine_version: "5.4.0",
    text_languages: ["eng"],
    text_corrected: false,
    text_updated_at: null,
    stale: false,
    created_at: "2026-01-01T00:00:00+00:00",
    updated_at: "2026-01-01T00:00:00+00:00",
  };
}

/** Exposes the pending insertion so the test can assert what would be written. */
function InsertionProbe() {
  const { insertion } = useWorkspaceActions();
  return <pre data-testid="insertion">{JSON.stringify(insertion)}</pre>;
}

function renderDialog(onOpenChange = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <WorkspaceActionsProvider>
        <RegionFormulaDialog
          projectId="project-1"
          element={element()}
          pageNumber={4}
          open
          onOpenChange={onOpenChange}
        />
        <InsertionProbe />
      </WorkspaceActionsProvider>
    </QueryClientProvider>,
  );
  return onOpenChange;
}

function insertion() {
  return JSON.parse(screen.getByTestId("insertion").textContent ?? "null");
}

function propose(latex = "E = mc^{2}") {
  return vi.spyOn(api, "createAiEquationProposal").mockResolvedValue({
    element_id: "element-1",
    page_id: "page-1",
    latex,
    provider: "ollama",
    model: "llava:7b",
    base_url: "http://127.0.0.1:11434",
  });
}

describe("region formula dialog", () => {
  it("starts from the stored region text", () => {
    renderDialog();
    expect(screen.getByLabelText("LaTeX source")).toHaveValue("E = mc^2");
  });

  it("inserts a reviewed display equation with the source note", () => {
    const onOpenChange = renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Insert as equation" }));

    const pending = insertion();
    expect(pending).toMatchObject({
      type: "equation",
      latex: "E = mc^2",
      numbered: false,
    });
    expect(pending.note).toContain("page 4");
    expect(pending.note).toContain("Unverified");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("can number the equation", () => {
    renderDialog();

    fireEvent.click(screen.getByLabelText("Show an equation number"));
    fireEvent.click(screen.getByRole("button", { name: "Insert as equation" }));

    expect(insertion().numbered).toBe(true);
  });

  it("refuses source that the local renderer rejects", () => {
    renderDialog();
    const insert = screen.getByRole("button", { name: "Insert as equation" });

    fireEvent.change(screen.getByLabelText("LaTeX source"), {
      target: { value: "\\frac{1" },
    });

    expect(insert).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("could not be rendered");

    fireEvent.change(screen.getByLabelText("LaTeX source"), {
      target: { value: "\\frac{1}{2}" },
    });
    expect(insert).toBeEnabled();
  });

  it("refuses empty source", () => {
    renderDialog();

    fireEvent.change(screen.getByLabelText("LaTeX source"), { target: { value: "  " } });

    expect(screen.getByRole("button", { name: "Insert as equation" })).toBeDisabled();
  });

  it("omits the note when the checkbox is cleared", () => {
    renderDialog();

    fireEvent.click(screen.getByLabelText("Add a source note to the document"));
    fireEvent.click(screen.getByRole("button", { name: "Insert as equation" }));

    expect(insertion().note).toBeNull();
  });

  it("cannot transcribe without a configured vision model", () => {
    mocks.visionModel = "";
    renderDialog();

    expect(
      screen.getByRole("button", { name: "Transcribe with AI" }),
    ).toBeDisabled();
    expect(
      screen.getByText(/Choose a vision model in Settings/),
    ).toBeInTheDocument();
  });

  it("prefills the review field with the model proposal", async () => {
    const transcribe = propose();
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Transcribe with AI" }));

    await waitFor(() =>
      expect(screen.getByLabelText("LaTeX source")).toHaveValue("E = mc^{2}"),
    );
    expect(transcribe).toHaveBeenCalledWith("project-1", "element-1");
    expect(screen.getByText(/Proposed by llava:7b/)).toBeInTheDocument();
  });

  it("credits the model only while its proposal is unchanged", async () => {
    propose();
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Transcribe with AI" }));
    await waitFor(() =>
      expect(screen.getByLabelText("LaTeX source")).toHaveValue("E = mc^{2}"),
    );

    fireEvent.click(screen.getByRole("button", { name: "Insert as equation" }));
    expect(insertion().note).toContain("proposed by llava:7b");

    fireEvent.change(screen.getByLabelText("LaTeX source"), {
      target: { value: "E = mc^2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Insert as equation" }));

    expect(insertion().note).not.toContain("llava:7b");
    expect(insertion().note).toContain("reviewed from the region crop");
  });
});
