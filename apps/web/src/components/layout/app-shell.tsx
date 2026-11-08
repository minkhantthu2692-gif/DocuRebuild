import { useTranslation } from "react-i18next";

import { AppHeader } from "@/components/layout/app-header";
import { StatusBar } from "@/components/layout/status-bar";
import { Outlet } from "react-router-dom";

export function AppShell() {
  return (
    <div className="app-ambient flex h-dvh flex-col overflow-hidden">
      <AppHeader />
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
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
