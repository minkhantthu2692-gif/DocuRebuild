import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentLayoutDialog } from "@/components/workspace/document-layout-dialog";
import { i18n, initI18n } from "@/i18n";

const mocks = vi.hoisted(() => ({
  layout: {
    header_text: "Running head",
    footer_text: "Draft",
    show_page_numbers: true,
    updated_at: "2026-01-01T00:00:00+00:00",
  },
  isPending: false,
  isError: false,
  mutate: vi.fn(),
}));

vi.mock("@/hooks/use-document", () => ({
  useDocumentLayout: () => ({
    data: mocks.layout,
    isPending: mocks.isPending,
    isError: mocks.isError,
    refetch: vi.fn(),
  }),
  useSaveDocumentLayout: () => ({
    mutate: mocks.mutate,
    isPending: false,
  }),
}));

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

beforeEach(() => {
  mocks.layout = {
    header_text: "Running head",
    footer_text: "Draft",
    show_page_numbers: true,
    updated_at: "2026-01-01T00:00:00+00:00",
  };
  mocks.isPending = false;
  mocks.isError = false;
  mocks.mutate.mockReset();
});

function renderDialog(onOpenChange = vi.fn()) {
  render(
    <DocumentLayoutDialog
      projectId="project-1"
      open
      onOpenChange={onOpenChange}
    />,
  );
  return onOpenChange;
}

describe("document layout dialog", () => {
  it("shows the saved header, footer and page-number choice", () => {
    renderDialog();

    expect(screen.getByLabelText("Header text")).toHaveValue("Running head");
    expect(screen.getByLabelText("Footer text")).toHaveValue("Draft");
    expect(screen.getByRole("switch", { name: /Add page numbers/ })).toBeChecked();
    expect(screen.getByText("12 / 200")).toBeInTheDocument();
  });

  it("explains the supported placeholders and that Word/PDF use them", () => {
    renderDialog();

    expect(screen.getByText("Placeholders")).toBeInTheDocument();
    expect(screen.getByText(/\{page\} current page/)).toBeInTheDocument();
    expect(screen.getByText(/\{title\} project title/)).toBeInTheDocument();
    expect(screen.getByText(/Markdown and plain text are not paginated/)).toBeInTheDocument();
  });

  it("saves edited values and the page-number choice", () => {
    const onOpenChange = renderDialog();
    mocks.mutate.mockImplementation(
      (_payload: unknown, options: { onSuccess: () => void }) => options.onSuccess(),
    );

    fireEvent.change(screen.getByLabelText("Header text"), {
      target: { value: "Chapter 2 · {title}" },
    });
    fireEvent.change(screen.getByLabelText("Footer text"), {
      target: { value: "Source: {title}" },
    });
    fireEvent.click(screen.getByRole("switch", { name: /Add page numbers/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save layout" }));

    expect(mocks.mutate).toHaveBeenCalledWith(
      {
        header_text: "Chapter 2 · {title}",
        footer_text: "Source: {title}",
        show_page_numbers: false,
      },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("shows a retry action when the layout cannot be loaded", () => {
    mocks.isError = true;
    renderDialog();

    expect(
      screen.getByText("The saved page layout could not be loaded."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save layout" })).toBeDisabled();
  });
});
