import { Lock, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { useAppMeta, useHealth } from "@/hooks/use-app";
import { cn } from "@/lib/utils";

export function StatusBar() {
  const { t } = useTranslation("common");
  const health = useHealth();
  const meta = useAppMeta();

  const offline = health.isError;
  const degraded = health.data?.status === "degraded";
  const statusLabel = offline
    ? t("status.offline")
    : degraded
      ? t("status.degraded")
      : t("status.ready");

  return (
    <footer className="glass-panel z-header flex h-statusbar shrink-0 items-center gap-2 border-x-0 border-b-0 px-3 text-2xs text-muted-foreground sm:gap-3">
      <span className="flex items-center gap-1.5" role="status">
        <span
          className={cn(
            "size-1.5 rounded-pill",
            offline ? "bg-destructive" : degraded ? "bg-warning" : "bg-success",
          )}
          aria-hidden="true"
        />
        <span className="truncate">{statusLabel}</span>
      </span>
      <span className="hidden text-border sm:inline" aria-hidden="true">
        /
      </span>
      <span className="hidden font-mono sm:inline">v{meta.data?.version ?? "0.1.0"}</span>

      <div className="ml-auto flex items-center gap-1.5">
        <Badge variant="outline" className="hidden border-transparent bg-background/60 sm:inline-flex">
          <ShieldCheck className="text-success" />
          {t("status.localFirst")}
        </Badge>
        <Badge variant="outline" className="hidden border-transparent bg-background/60 md:inline-flex">
          <Lock className="text-primary" />
          {t("status.private")}
        </Badge>
      </div>
    </footer>
  );
}
