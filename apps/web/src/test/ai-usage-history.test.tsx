import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  AiUsageHistoryEntry,
  AiUsageHistoryResponse,
} from "@docurebuild/shared-types";

import { AiUsageHistoryDialog } from "@/components/settings/ai-usage-history-dialog";
import { i18n, initI18n } from "@/i18n";
import type { AiUsageHistoryParams } from "@/hooks/use-ai";

const mocks = vi.hoisted(() => ({
  params: [] as unknown[],
  data: undefined as unknown,
  isLoading: false,
  isError: false,
  isFetching: false,
  refetch: vi.fn(),
}));

vi.mock("@/hooks/use-ai", () => ({
  useAiUsageHistory: (params: unknown) => {
    mocks.params.push(params);
    return {
      data: mocks.data,
      isLoading: mocks.isLoading,
      isError: mocks.isError,
      isFetching: mocks.isFetching,
      refetch: mocks.refetch,
    };
  },
}));

const entry = (
  patch: Partial<AiUsageHistoryEntry> & Pick<AiUsageHistoryEntry, "id">,
): AiUsageHistoryEntry => ({
  provider: "ollama",
  model: "qwen2.5:7b",
  task: "ocr_cleanup",
  outcome: "success",
  error_code: null,
  project_id: "project-1",
  page_id: null,
  block_id: null,
  connection_id: null,
  connection_name: null,
  key_id: null,
  key_label: null,
  input_tokens: null,
  output_tokens: null,
  total_tokens: null,
  estimated_cost_usd: null,
  cost_source: null,
  duration_ms: null,
  created_at: "2026-11-12T09:30:00",
  project_name: "Quantum Mechanics",
  ...patch,
});

const response = (
  patch: Partial<AiUsageHistoryResponse> = {},
): AiUsageHistoryResponse => ({
  entries: [entry({ id: "usage-1" })],
  total: 1,
  limit: 25,
  offset: 0,
  ...patch,
});

function renderDialog() {
  render(<AiUsageHistoryDialog open onOpenChange={vi.fn()} />);
}

function lastParams(): AiUsageHistoryParams {
  return mocks.params[mocks.params.length - 1] as AiUsageHistoryParams;
}

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

beforeEach(() => {
  mocks.params.length = 0;
  mocks.data = response();
  mocks.isLoading = false;
  mocks.isError = false;
  mocks.isFetching = false;
  mocks.refetch.mockReset();
});

describe("AI usage history dialog", () => {
  it("lists ledger rows with task, project, model and outcome", () => {
    mocks.data = response({
      total: 2,
      entries: [
        entry({ id: "usage-1", model: "cleanup-model" }),
        entry({
          id: "usage-2",
          task: "equation_transcription",
          outcome: "error",
          error_code: "ai_timeout",
          model: "vision-model",
          project_name: null,
        }),
      ],
    });
    renderDialog();

    expect(screen.getByRole("heading", { name: "AI usage history" })).toBeInTheDocument();
    expect(screen.getByText("OCR text cleanup")).toBeInTheDocument();
    expect(screen.getByText("Equation transcription")).toBeInTheDocument();
    expect(screen.getByText("Quantum Mechanics")).toBeInTheDocument();
    expect(screen.getByText("No project")).toBeInTheDocument();
    expect(screen.getByText("ai_timeout")).toBeInTheDocument();
    expect(screen.getByText("cleanup-model")).toBeInTheDocument();
    expect(screen.getByText("vision-model")).toBeInTheDocument();
    expect(screen.getByText("Showing 1–2 of 2")).toBeInTheDocument();
  });

  it("sends outcome and task filters from the first page", async () => {
    renderDialog();

    fireEvent.click(screen.getByRole("combobox", { name: "Outcome" }));
    fireEvent.keyDown(await screen.findByRole("option", { name: "Failed" }), {
      key: "Enter",
    });
    expect(lastParams()).toMatchObject({ offset: 0, outcome: "error" });

    fireEvent.click(screen.getByRole("combobox", { name: "Task" }));
    fireEvent.keyDown(
      await screen.findByRole("option", { name: "Region proposals" }),
      { key: "Enter" },
    );
    expect(lastParams()).toMatchObject({
      offset: 0,
      outcome: "error",
      task: "region_proposals",
    });
  });

  it("pages forward and back without changing filters", () => {
    mocks.data = response({
      entries: Array.from({ length: 25 }, (_, index) =>
        entry({ id: `usage-${index}` }),
      ),
      total: 30,
    });
    renderDialog();

    expect(screen.getByText("Showing 1–25 of 30")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(lastParams()).toMatchObject({ limit: 25, offset: 25 });

    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(lastParams()).toMatchObject({ limit: 25, offset: 0 });
  });

  it("explains an empty page and a failed load", () => {
    mocks.data = response({ entries: [], total: 0 });
    const { unmount } = render(
      <AiUsageHistoryDialog open onOpenChange={vi.fn()} />,
    );
    expect(screen.getByText("No matching requests")).toBeInTheDocument();
    unmount();

    mocks.isError = true;
    renderDialog();
    expect(
      screen.getByText("The local usage history could not be loaded."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(mocks.refetch).toHaveBeenCalledTimes(1);
  });
});
