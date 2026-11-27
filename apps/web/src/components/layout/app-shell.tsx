import { useTranslation } from "react-i18next";

import { AppHeader } from "@/components/layout/app-header";
import { StatusBar } from "@/components/layout/status-bar";
import { Outlet } from "react-router-dom";

export function AppShell() {
  const { t } = useTranslation("common");
  return (
    <div className="app-ambient flex h-dvh flex-col overflow-hidden">
      <a
        href="#main-content"
        className="focus-ring fixed left-3 top-3 z-[var(--z-overlay)] -translate-y-24 rounded-md bg-background px-3 py-2 text-sm font-medium text-foreground shadow-lg focus:translate-y-0"
      >
        {t("actions.skipToContent")}
      </a>
      <AppHeader />
      <main id="main-content" tabIndex={-1} className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>
      <StatusBar />
    </div>
  );
}

export function PagePlaceholder() {
  const { t } = useTranslation("common");
  return <div className="p-6 text-sm text-muted-foreground">{t("loading")}</div>;
}
