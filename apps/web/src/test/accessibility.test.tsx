import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/layout/app-shell";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { i18n, initI18n } from "@/i18n";

vi.mock("@/components/layout/app-header", () => ({
  AppHeader: () => <header><button type="button">Header action</button></header>,
}));

vi.mock("@/components/layout/status-bar", () => ({
  StatusBar: () => <footer>Status</footer>,
}));

beforeAll(async () => {
  initI18n();
  await i18n.changeLanguage("en");
});

describe("installed-app accessibility primitives", () => {
  it("provides a keyboard skip link and a focusable main landmark", () => {
    render(
      <MemoryRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Outlet />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    const skipLink = screen.getByRole("link", { name: "Skip to main content" });
    expect(skipLink).toHaveAttribute("href", "#main-content");
    expect(document.querySelector("#main-content")).toHaveAttribute("tabindex", "-1");
  });

  it("traps dialog focus and restores it after Escape", async () => {
    render(
      <Dialog>
        <DialogTrigger>Open dialog</DialogTrigger>
        <DialogContent>
          <DialogTitle>Accessible dialog</DialogTitle>
          <DialogDescription>Dialog description</DialogDescription>
          <button type="button">First action</button>
          <button type="button">Last action</button>
        </DialogContent>
      </Dialog>,
    );

    const trigger = screen.getByRole("button", { name: "Open dialog" });
    trigger.focus();
    fireEvent.click(trigger);

    expect(await screen.findByRole("dialog", { name: "Accessible dialog" })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape", code: "Escape" });

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(trigger).toHaveFocus();
    });
  });
});
