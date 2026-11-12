import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { HistoryEvent } from "@docurebuild/shared-types";

import { ProjectActivityDialog } from "@/components/workspace/project-activity-dialog";
import { i18n, initI18n } from "@/i18n";

const mocks = vi.hoisted(() => ({
  refetch: vi.fn(),
  events: [] as HistoryEvent[],
  isLoading: false,
  isError: false,
}));

vi.mock("@/hooks/use-projects", () => ({
  useProjectHistory: () => ({
    data: mocks.events,
    isLoading: mocks.isLoading,
    isError: mocks.isError,
    isFetching: false,
    refetch: mocks.refetch,
  }),
}));

const event = (patch: Partial<HistoryEvent> & Pick<HistoryEvent, "id">): HistoryEvent => ({
  event_type: "project_created",
  summary: "",
  payload: {},
  created_at: "2026-11-12T09:30:00+00:00",
  ...patch,
});

function renderDialog() {
  const onOpenChange = vi.fn();
  render(
    <ProjectActivityDialog
      projectId="project-1"
      open
      onOpenChange={onOpenChange}
    />,
  );
  return { onOpenChange };
}

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

beforeEach(() => {
  mocks.events = [];
  mocks.isLoading = false;
  mocks.isError = false;
  mocks.refetch.mockReset();
});

describe("ProjectActivityDialog", () => {
  it("labels known local events and shows their metadata", () => {
    mocks.events = [
      event({
        id: "1",
        event_type: "document_exported",
        payload: { format: "markdown", byte_size: 2048 },
        created_at: "2026-11-12T10:00:00+00:00",
      }),
      event({
        id: "2",
        event_type: "ocr_succeeded",
        payload: {
          languages: "eng",
          mean_confidence: 91.5,
          blocks: 4,
        },
        created_at: "2026-11-12T09:45:00+00:00",
      }),
      event({
        id: "3",
        event_type: "pages_imported",
        payload: { count: 2, cancelled: false },
        created_at: "2026-11-12T09:30:00+00:00",
      }),
      event({
        id: "4",
        event_type: "project_created",
        created_at: "2026-11-12T09:00:00+00:00",
      }),
    ];
    renderDialog();

    expect(screen.getByText("4 events")).toBeInTheDocument();
    expect(screen.getByText("Document exported")).toBeInTheDocument();
    expect(screen.getByText(/Format: Markdown \(\.md\)/)).toBeInTheDocument();
    expect(screen.getByText("Text extraction completed")).toBeInTheDocument();
    expect(screen.getByText(/Languages: eng/)).toBeInTheDocument();
    expect(screen.getByText(/Mean confidence: 91.5/)).toBeInTheDocument();
    expect(screen.getByText(/4 text blocks/)).toBeInTheDocument();
    expect(screen.getByText("Pages imported")).toBeInTheDocument();
    expect(screen.getByText("2 pages imported")).toBeInTheDocument();
    expect(screen.getByText("Project created")).toBeInTheDocument();
  });

  it("filters by localized search text and clears the filter", () => {
    mocks.events = [
      event({
        id: "export",
        event_type: "document_exported",
        payload: { format: "markdown", byte_size: 2048 },
      }),
      event({
        id: "ocr",
        event_type: "ocr_succeeded",
        payload: { languages: "eng", mean_confidence: 91.5, blocks: 2 },
      }),
      event({
        id: "import",
        event_type: "pages_imported",
        payload: { count: 2, cancelled: false },
      }),
    ];
    renderDialog();

    expect(screen.getByRole("combobox", { name: "Event type" })).toBeInTheDocument();
    const search = screen.getByRole("searchbox", { name: "Search activity" });
    fireEvent.change(search, { target: { value: "Text extraction" } });

    expect(screen.getByText("Text extraction completed")).toBeInTheDocument();
    expect(screen.queryByText("Document exported")).not.toBeInTheDocument();
    expect(screen.queryByText("Pages imported")).not.toBeInTheDocument();
    expect(screen.getByText("1 of 3 events")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    expect(screen.getByText("3 events")).toBeInTheDocument();
    expect(screen.getByText("Document exported")).toBeInTheDocument();
    expect(screen.getByText("Pages imported")).toBeInTheDocument();
  });

  it("shows a filter-specific empty state with a way back", () => {
    mocks.events = [
      event({ id: "export", event_type: "document_exported", payload: { format: "txt" } }),
      event({ id: "import", event_type: "pages_imported", payload: { count: 1 } }),
    ];
    renderDialog();

    fireEvent.change(screen.getByRole("searchbox", { name: "Search activity" }), {
      target: { value: "no such event" },
    });

    expect(screen.getByText("No matching events")).toBeInTheDocument();
    expect(screen.getByText("0 of 2 events")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show all events" }));

    expect(screen.getByText("2 events")).toBeInTheDocument();
    expect(screen.getByText("Document exported")).toBeInTheDocument();
  });

  it("keeps unknown events visible with their recorded summary", () => {
    mocks.events = [
      event({
        id: "legacy",
        event_type: "future_event_type",
        summary: "Something new happened",
      }),
    ];
    renderDialog();

    expect(screen.getByText("Other event")).toBeInTheDocument();
    expect(screen.getByText("Something new happened")).toBeInTheDocument();
  });

  it("shows an empty state when nothing has been recorded", () => {
    renderDialog();
    expect(screen.getByText("No activity yet")).toBeInTheDocument();
  });

  it("offers a retry when loading fails", async () => {
    mocks.isError = true;
    renderDialog();

    expect(screen.getByText("The activity log could not be loaded.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(mocks.refetch).toHaveBeenCalledTimes(1));
  });
});
