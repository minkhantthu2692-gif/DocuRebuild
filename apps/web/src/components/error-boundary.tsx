import type { ErrorInfo, ReactNode } from "react";
import { Component } from "react";

import { i18n } from "@/i18n";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Local-only logging. Never send error data to a remote service.
    console.error("DocuRebuild UI error", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="app-ambient flex min-h-dvh items-center justify-center p-6">
          <div className="glass-panel max-w-md rounded-xl p-8 text-center shadow-lg">
            <h1 className="text-lg font-semibold tracking-tight">
              {i18n.t("errors:internal_error")}
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">{i18n.t("errors:generic")}</p>
            <button
              type="button"
              className="focus-ring mt-5 inline-flex h-control items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
              onClick={() => window.location.reload()}
            >
              {i18n.t("common:actions.retry")}
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
