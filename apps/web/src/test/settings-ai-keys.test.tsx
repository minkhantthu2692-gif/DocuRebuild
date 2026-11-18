import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { SettingsPage } from "@/pages/settings-page";
import { i18n, initI18n } from "@/i18n";

const mocks = vi.hoisted(() => ({
  update: vi.fn(),
  probe: vi.fn(),
  usage: {
    current: null as null | {
      window_hours: number;
      request_limit: number;
      used: number;
      remaining: number | null;
      successful: number;
      failed: number;
      by_task: Array<{ task: string; used: number }>;
      recent: unknown[];
    },
  },
}));

const settings = {
  language: "en" as const,
  appearance: {
    theme: "system" as const,
    accent: "indigo" as const,
    radius: "soft" as const,
    blur: "subtle" as const,
    density: "comfortable" as const,
    font_size: "md" as const,
    motion: "full" as const,
  },
  editor: { document_font: "serif" as const },
  export: { pdf_page_size: "a4" as const, pdf_margin: "normal" as const },
  ai: {
    text: {
      provider: "openai_compatible" as const,
      base_url: "http://127.0.0.1:1234/v1",
      model: "local-model",
      allow_remote: false,
      cost_class: "local" as const,
      has_api_key: true,
    },
    vision: {
      provider: "ollama" as const,
      base_url: "",
      model: "",
      allow_remote: false,
      cost_class: "local" as const,
      has_api_key: false,
    },
    request_limit: 0,
  },
  backups: { auto_on_open: false, interval_hours: 24, keep_copies: 5 },
};

vi.mock("@/hooks/use-app", () => ({
  useAppMeta: () => ({ data: undefined }),
  useAppSettings: () => ({ data: settings, isLoading: false }),
  useHealth: () => ({ data: undefined }),
  useUpdateSettings: () => ({ mutate: mocks.update, isPending: false }),
}));

vi.mock("@/hooks/use-ai", () => ({
  useAiProviders: () => ({ data: undefined }),
  useAiUsage: () => ({ data: mocks.usage.current, isError: false }),
  useAiUsageHistory: () => ({ data: undefined, isLoading: false, isError: false }),
  useProbeAiProvider: () => ({ mutate: mocks.probe, isPending: false }),
}));

vi.mock("@/hooks/use-ocr", () => ({
  useOcrCapabilities: () => ({ data: undefined, isLoading: false, isFetching: false }),
}));

function renderPage() {
  render(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>,
  );
}

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

beforeEach(() => {
  mocks.update.mockReset();
  mocks.probe.mockReset();
  mocks.usage.current = null;
});

describe("AI API keys", () => {
  it("shows that a key is saved and sends a replacement only on save", () => {
    renderPage();

    expect(screen.getByText("Key saved")).toBeInTheDocument();
    const input = screen.getByLabelText("Text cleanup server: API key");
    fireEvent.change(input, { target: { value: "  sk-new-key  " } });

    expect(mocks.update).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Save AI settings" }));

    expect(mocks.update).toHaveBeenCalledWith(
      expect.objectContaining({
        ai: expect.objectContaining({
          text: expect.objectContaining({ api_key: "sk-new-key" }),
        }),
      }),
      expect.any(Object),
    );
    const payload = mocks.update.mock.calls[0][0] as {
      ai: { text: Record<string, unknown> };
    };
    expect(payload.ai.text).not.toHaveProperty("clear_api_key");
  });

  it("asks to remove the saved key on the next save", () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Remove key" }));
    expect(
      screen.getByText("The saved key will be removed when you save."),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Save AI settings" }));

    const payload = mocks.update.mock.calls[0][0] as {
      ai: { text: Record<string, unknown> };
    };
    expect(payload.ai.text.clear_api_key).toBe(true);
    expect(payload.ai.text).not.toHaveProperty("api_key");
  });

  it("tests an unsaved key with the text task profile", () => {
    renderPage();

    fireEvent.change(screen.getByLabelText("Text cleanup server: API key"), {
      target: { value: "sk-probe" },
    });
    fireEvent.click(
      screen.getByRole("button", {
        name: "Text cleanup server: Test connection",
      }),
    );

    expect(mocks.probe).toHaveBeenCalledWith(
      expect.objectContaining({
        task: "text",
        api_key: "sk-probe",
        provider: "openai_compatible",
      }),
      expect.any(Object),
    );
  });

  it("saves the cost class chosen for a profile", () => {
    renderPage();

    const costClass = screen.getByLabelText("Text cleanup server: Cost class");
    fireEvent.click(within(costClass).getByText("Paid"));
    fireEvent.click(screen.getByRole("button", { name: "Save AI settings" }));

    const payload = mocks.update.mock.calls[0][0] as {
      ai: { text: Record<string, unknown> };
    };
    expect(payload.ai.text.cost_class).toBe("paid");
  });

  it("marks a remote URL as paid but keeps a declared free tier", () => {
    renderPage();

    fireEvent.change(screen.getByLabelText("Text cleanup server: Server URL"), {
      target: { value: "https://api.example.com/v1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save AI settings" }));

    const escalated = mocks.update.mock.calls[0][0] as {
      ai: { text: Record<string, unknown> };
    };
    expect(escalated.ai.text.base_url).toBe("https://api.example.com/v1");
    expect(escalated.ai.text.cost_class).toBe("paid");

    const visionCostClass = screen.getByLabelText(
      "Image analysis server: Cost class",
    );
    fireEvent.click(within(visionCostClass).getByText("Free"));
    fireEvent.change(screen.getByLabelText("Image analysis server: Server URL"), {
      target: { value: "https://free.example.com/v1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save AI settings" }));

    const kept = mocks.update.mock.calls[1][0] as {
      ai: { vision: Record<string, unknown> };
    };
    expect(kept.ai.vision.cost_class).toBe("free");
  });

  it("explains a provider rate limit and its advisory wait", () => {
    mocks.probe.mockImplementation(
      (
        _payload: unknown,
        options?: { onSuccess?: (result: unknown) => void },
      ) => {
        options?.onSuccess?.({
          status: "http_error",
          provider: "openai_compatible",
          base_url: "http://127.0.0.1:1234/v1",
          models: [],
          version: null,
          error_code: "ai_rate_limited",
          http_status: 429,
          retry_after_seconds: 30,
        });
      },
    );
    renderPage();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Text cleanup server: Test connection",
      }),
    );

    expect(screen.getByText(/rate limiting requests/)).toBeInTheDocument();
    expect(screen.getByText(/wait 30 seconds/)).toBeInTheDocument();
    expect(screen.getByText(/does not retry on its own/)).toBeInTheDocument();
  });

  it("describes a discovered model and warns about an unlisted one", () => {
    mocks.probe.mockImplementation(
      (
        _payload: unknown,
        options?: { onSuccess?: (result: unknown) => void },
      ) => {
        options?.onSuccess?.({
          status: "ready",
          provider: "openai_compatible",
          base_url: "http://127.0.0.1:1234/v1",
          models: [
            { id: "local-model", family: "qwen2", parameter_size: "7.6B" },
            { id: "small-model", family: "llama", parameter_size: "1.2B" },
          ],
          version: null,
          error_code: null,
          http_status: null,
          retry_after_seconds: null,
        });
      },
    );
    renderPage();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Text cleanup server: Test connection",
      }),
    );

    expect(screen.getByText(/Listed by the server/)).toBeInTheDocument();
    expect(screen.getByText(/Family: qwen2/)).toBeInTheDocument();
    expect(screen.getByText(/Parameters: 7.6B/)).toBeInTheDocument();
    expect(screen.queryByText(/did not list this model/)).not.toBeInTheDocument();

    const option = document.querySelector('option[value="small-model"]');
    expect(option?.getAttribute("label")).toBe("llama · 1.2B");

    fireEvent.change(screen.getByLabelText("Text model"), {
      target: { value: "missing-model" },
    });
    expect(screen.getByText(/did not list this model/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Text model"), {
      target: { value: "small-model" },
    });
    expect(screen.getByText(/Family: llama/)).toBeInTheDocument();
    expect(screen.queryByText(/did not list this model/)).not.toBeInTheDocument();
  });

  it("breaks the rolling request budget down by task", () => {
    mocks.usage.current = {
      window_hours: 24,
      request_limit: 10,
      used: 4,
      remaining: 6,
      successful: 3,
      failed: 1,
      by_task: [
        { task: "ocr_cleanup", used: 2 },
        { task: "equation_transcription", used: 1 },
        { task: "legacy_task", used: 1 },
      ],
      recent: [],
    };
    renderPage();

    expect(screen.getByText("By task, last 24 hours")).toBeInTheDocument();
    expect(screen.getByText("OCR text cleanup: 2")).toBeInTheDocument();
    expect(screen.getByText("Equation transcription: 1")).toBeInTheDocument();
    // A task name this build does not know is counted, not hidden.
    expect(screen.getByText("Other task: 1")).toBeInTheDocument();
  });

  it("hides the breakdown before the first request", () => {
    mocks.usage.current = {
      window_hours: 24,
      request_limit: 10,
      used: 0,
      remaining: 10,
      successful: 0,
      failed: 0,
      by_task: [],
      recent: [],
    };
    renderPage();

    expect(
      screen.queryByText("By task, last 24 hours"),
    ).not.toBeInTheDocument();
  });
});
