import { ShieldAlert } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { AiTaskStatus } from "@docurebuild/shared-types";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { needsPaidApproval } from "@/lib/ai-cost";

interface PendingApproval {
  status: AiTaskStatus;
  resolve: (approved: boolean) => void;
}

/**
 * Ask once, per action, before a paid AI route sends anything.
 *
 * The hook resolves to `true` immediately for local and free routes. Only a
 * remote route that is not declared free opens the dialog, so the user always
 * knows which request may cost money. The backend enforces the same rule.
 */
export function usePaidAiGuard() {
  const { t } = useTranslation("workspace");
  const { t: tCommon } = useTranslation("common");
  const [pending, setPending] = useState<PendingApproval | null>(null);
  const pendingRef = useRef<PendingApproval | null>(null);

  const settle = useCallback((approved: boolean) => {
    const current = pendingRef.current;
    pendingRef.current = null;
    setPending(null);
    current?.resolve(approved);
  }, []);

  const requestApproval = useCallback(
    (status: AiTaskStatus | undefined): Promise<boolean> => {
      if (!needsPaidApproval(status)) return Promise.resolve(true);
      return new Promise<boolean>((resolve) => {
        const entry = { status: status as AiTaskStatus, resolve };
        pendingRef.current = entry;
        setPending(entry);
      });
    },
    [],
  );

  const paidDialog = (
    <Dialog
      open={pending !== null}
      onOpenChange={(open) => {
        if (!open) settle(false);
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldAlert className="size-icon-sm text-warning" aria-hidden="true" />
            {t("paidAi.title")}
          </DialogTitle>
          <DialogDescription>{t("paidAi.description")}</DialogDescription>
        </DialogHeader>

        {pending ? (
          <div className="space-y-2 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="warning">{t("paidAi.badge")}</Badge>
              <span className="min-w-0 break-words">
                {pending.status.model_display_name ||
                  pending.status.model_id ||
                  t("paidAi.unknownModel")}
              </span>
            </div>
            {pending.status.connection_name ? (
              <p className="text-2xs text-muted-foreground">
                {pending.status.connection_name}
              </p>
            ) : null}
            <p className="break-all text-2xs text-muted-foreground">
              {pending.status.base_url || t("paidAi.defaultServer")}
            </p>
            <p className="text-2xs leading-relaxed text-muted-foreground">
              {t("paidAi.costNote")}
            </p>
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => settle(false)}>
            {tCommon("actions.cancel")}
          </Button>
          <Button variant="destructive" onClick={() => settle(true)}>
            {t("paidAi.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  return { requestApproval, paidDialog };
}
