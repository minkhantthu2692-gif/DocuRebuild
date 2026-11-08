import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { Route, Routes } from "react-router-dom";
import { lazy, Suspense } from "react";

import { ErrorBoundary } from "@/components/error-boundary";
import { AppShell, PagePlaceholder } from "@/components/layout/app-shell";
import { TooltipProvider } from "@/components/ui/tooltip";
import { DashboardPage } from "@/pages/dashboard-page";
import { NotFoundPage } from "@/pages/not-found-page";
import { AppearanceSync } from "@/providers/appearance-sync";
import { DEFAULT_APPEARANCE, resolveTheme } from "@/lib/appearance";
import { useAppSettings } from "@/hooks/use-app";

const WorkspacePage = lazy(() =>
  import("@/pages/workspace-page").then((module) => ({ default: module.WorkspacePage })),
);
const SettingsPage = lazy(() =>
  import("@/pages/settings-page").then((module) => ({ default: module.SettingsPage })),
);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});

function ThemedToaster() {
  const { data } = useAppSettings();
  const theme = resolveTheme(data?.appearance.theme ?? DEFAULT_APPEARANCE.theme);
  return (
    <Toaster
      theme={theme}
      position="bottom-right"
      closeButton
      toastOptions={{
        classNames: {
          toast: "!bg-card !text-card-foreground !border-border !shadow-lg",
          description: "!text-muted-foreground",
        },
      }}
    />
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <TooltipProvider delayDuration={250} skipDelayDuration={200}>
          <AppearanceSync />
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<DashboardPage />} />
              <Route
                path="projects/:projectId"
                element={
                  <Suspense fallback={<PagePlaceholder />}>
                    <WorkspacePage />
                  </Suspense>
                }
              />
              <Route
                path="settings"
                element={
                  <Suspense fallback={<PagePlaceholder />}>
                    <SettingsPage />
                  </Suspense>
                }
              />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Routes>
          <ThemedToaster />
        </TooltipProvider>
      </ErrorBoundary>
    </QueryClientProvider>
  );
}
