import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { SettingsPage } from "@/pages/settings-page";
import { i18n, initI18n } from "@/i18n";

const mocks = vi.hoisted(() => ({
  update: vi.fn(),
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
    text: { provider: "ollama" as const, base_url: "", model: "", allow_remote: false },
    vision_model: "",
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
  useAiUsage: () => ({ data: undefined, isError: false }),
  useProbeAiProvider: () => ({ mutate: vi.fn(), isPending: false }),
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
});

describe("export settings", () => {
  it("shows the PDF layout section with the saved values", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "PDF layout" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Page size" })).toHaveTextContent(
      "A4 (210 × 297 mm)",
    );
    expect(screen.getByRole("combobox", { name: "Margin" })).toHaveTextContent(
      "Normal",
    );
    expect(
      screen.getByText(/These settings apply to PDF export only/),
    ).toBeInTheDocument();
  });

  it("saves a Letter page size without changing other settings", async () => {
    renderPage();

    const trigger = screen.getByRole("combobox", { name: "Page size" });
    fireEvent.click(trigger);
    const option = await screen.findByRole("option", {
      name: "Letter (8.5 × 11 in)",
    });
    fireEvent.keyDown(option, { key: "Enter" });

    expect(mocks.update).toHaveBeenCalledWith(
      { export: { pdf_page_size: "letter" } },
      expect.any(Object),
    );
  });
});
