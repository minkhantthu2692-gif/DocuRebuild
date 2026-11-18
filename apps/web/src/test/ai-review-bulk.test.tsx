import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { AiSuggestion } from "@docurebuild/shared-types";

import { AiReviewDialog } from "@/components/workspace/ai-review-dialog";
import { i18n, initI18n } from "@/i18n";

const mocks = vi.hoisted(() => ({
  suggestions: [] as unknown[],
  isLoading: false,
  isError: false,
  decidePending: false,
  bulkPending: false,
  refetch: vi.fn(),
  decideMutate: vi.fn(),
  bulkMutate: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    success: mocks.success,
    warning: mocks.warning,
    error: mocks.error,
  },
}));

vi.mock("@/hooks/use-ai", () => ({
  useProjectAiSuggestions: () => ({
    data: { suggestions: mocks.suggestions },
    isLoading: mocks.isLoading,
    isError: mocks.isError,
    isFetching: false,
    refetch: mocks.refetch,
  }),
  useDecideAiSuggestion: () => ({
    mutate: mocks.decideMutate,
    isPending: mocks.decidePending,
    variables: undefined,
  }),
  useBulkDecideAiSuggestions: () => ({
    mutate: mocks.bulkMutate,
    isPending: mocks.bulkPending,
  }),
}));

const suggestion = (
  patch: Partial<AiSuggestion> & Pick<AiSuggestion, "id">,
): AiSuggestion => ({
  page_id: "page-1",
  page_number: 3,
  block_id: "block-1",
  task: "ocr_cleanup",
  original_text: "Chapter One",
  proposed_text: "Chapter One (cleaned)",
  provider: "ollama",
  model: "qwen2.5:7b",
  base_url: "http://127.0.0.1:11434",
  status: "pending",
  created_at: "2026-11-12T09:30:00",
  updated_at: "2026-11-12T09:30:00",
  ...patch,
});

function renderDialog() {
  render(<AiReviewDialog projectId="project-1" open onOpenChange={vi.fn()} />);
}

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

beforeEach(() => {
  mocks.suggestions = [
    suggestion({ id: "suggestion-1" }),
    suggestion({
      id: "suggestion-2",
      page_id: "page-2",
      page_number: 4,
      original_text: "A local OCR result.",
    }),
  ];
  mocks.isLoading = false;
  mocks.isError = false;
  mocks.decidePending = false;
  mocks.bulkPending = false;
  mocks.refetch.mockReset();
  mocks.decideMutate.mockReset();
  mocks.bulkMutate.mockReset();
  mocks.success.mockReset();
  mocks.warning.mockReset();
  mocks.error.mockReset();
});

describe("AI proposal bulk review", () => {
  it("accepts every selected proposal only after confirmation", () => {
    mocks.bulkMutate.mockImplementation(
      (
        payload: { ids: string[]; status: "accepted" | "rejected" },
        options?: { onSuccess?: (result: unknown) => void },
      ) => {
        options?.onSuccess?.({
          results: payload.ids.map((id) => ({
            id,
            status: payload.status,
            error_code: null,
          })),
          requested: payload.ids.length,
          succeeded: payload.ids.length,
          failed: 0,
        });
      },
    );
    renderDialog();

    expect(screen.getByText("0 selected")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("checkbox", { name: "Select all pending proposals" }),
    );
    expect(screen.getByText("2 selected")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Accept selected" }));
    expect(mocks.bulkMutate).not.toHaveBeenCalled();
    expect(
      screen.getByText(/Accept 2 selected proposals\? Each one is re-checked/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Accept 2" }));
    expect(mocks.bulkMutate).toHaveBeenCalledWith(
      { ids: ["suggestion-1", "suggestion-2"], status: "accepted" },
      expect.any(Object),
    );
    expect(mocks.success).toHaveBeenCalledWith(
      "2 proposals accepted. Review each block against its source page.",
    );
    expect(screen.getByText("0 selected")).toBeInTheDocument();
  });

  it("rejects a single selected proposal and reports a partial result", () => {
    mocks.bulkMutate.mockImplementation(
      (
        payload: { ids: string[]; status: "accepted" | "rejected" },
        options?: { onSuccess?: (result: unknown) => void },
      ) => {
        options?.onSuccess?.({
          results: [
            { id: payload.ids[0], status: null, error_code: "ai_suggestion_stale" },
          ],
          requested: payload.ids.length,
          succeeded: 0,
          failed: 1,
        });
      },
    );
    renderDialog();

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Select the proposal for Page 3 starting with Chapter One",
      }),
    );
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reject selected" }));
    expect(
      screen.getByText(/Reject 1 selected proposals\? Their OCR text stays unchanged/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reject 1" }));
    expect(mocks.bulkMutate).toHaveBeenCalledWith(
      { ids: ["suggestion-1"], status: "rejected" },
      expect.any(Object),
    );
    expect(mocks.error).toHaveBeenCalledWith(
      "No proposals were updated. 1 could not be applied.",
    );
    expect(screen.getByText("0 selected")).toBeInTheDocument();
  });

  it("keeps the single-proposal actions working", () => {
    mocks.decideMutate.mockImplementation(
      (
        _payload: unknown,
        options?: { onSuccess?: () => void },
      ) => {
        options?.onSuccess?.();
      },
    );
    renderDialog();

    fireEvent.click(screen.getAllByRole("button", { name: "Accept" })[0]);
    expect(mocks.decideMutate).toHaveBeenCalledWith(
      { suggestionId: "suggestion-1", payload: { status: "accepted" } },
      expect.any(Object),
    );
    expect(mocks.success).toHaveBeenCalledWith(
      "Proposal accepted. Review the block against the source page.",
    );
  });

  it("marks the characters a proposal changed", () => {
    mocks.suggestions = [
      suggestion({
        id: "suggestion-1",
        original_text: "tbe fox",
        proposed_text: "the fox",
      }),
    ];
    const { baseElement } = render(
      <AiReviewDialog projectId="project-1" open onOpenChange={vi.fn()} />,
    );

    expect(baseElement.querySelector("del")?.textContent).toBe("b");
    expect(baseElement.querySelector("ins")?.textContent).toBe("h");
    expect(
      screen.getByText(
        "Struck-through text is only in the current OCR text; underlined text is only in the proposal.",
      ),
    ).toBeInTheDocument();
  });

  it("keeps both panels readable when the proposal is unchanged", () => {
    mocks.suggestions = [
      suggestion({
        id: "suggestion-1",
        original_text: "Same text",
        proposed_text: "Same text",
      }),
    ];
    renderDialog();

    expect(screen.getAllByText("Same text")).toHaveLength(2);
    expect(screen.queryByText(/Struck-through text/)).not.toBeInTheDocument();
  });
});
