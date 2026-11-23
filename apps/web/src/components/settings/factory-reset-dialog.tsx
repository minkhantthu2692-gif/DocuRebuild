import { TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useFactoryReset } from "@/hooks/use-app";
import { clearClientCaches } from "@/lib/client-caches";

const CONFIRMATION = "DELETE";

interface FactoryResetDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  dataDir?: string;
}

export function FactoryResetDialog({
  open,
  onOpenChange,
  dataDir,
}: FactoryResetDialogProps) {
  const { t } = useTranslation("settings");
  const { t: tCommon } = useTranslation("common");
  const reset = useFactoryReset();
  const errorMessage = useApiErrorMessage();
  const [confirmation, setConfirmation] = useState("");

  useEffect(() => {
    if (!open) setConfirmation("");
  }, [open]);

  const matches = confirmation === CONFIRMATION;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("storage.reset.dialogTitle")}</DialogTitle>
          <DialogDescription>{t("storage.reset.dialogDescription")}</DialogDescription>
        </DialogHeader>

        <div className="mt-4 flex gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-xs leading-relaxed">
          <TriangleAlert
            className="mt-0.5 size-icon-sm shrink-0 text-destructive"
            aria-hidden="true"
          />
          <div className="space-y-2">
            <p className="font-medium text-foreground">{t("storage.reset.warning")}</p>
            <ul className="list-disc space-y-1 pl-4 text-muted-foreground">
              <li>{t("storage.reset.items.projects")}</li>
              <li>{t("storage.reset.items.settings")}</li>
              <li>{t("storage.reset.items.keys")}</li>
              <li>{t("storage.reset.items.backups")}</li>
            </ul>
            <p className="text-muted-foreground">{t("storage.reset.irreversible")}</p>
          </div>
        </div>

        {dataDir ? (
          <p className="mt-3 break-all font-mono text-2xs text-muted-foreground">
            {dataDir}
          </p>
        ) : null}

        <div className="mt-4 space-y-1.5">
          <Label htmlFor="factory-reset-confirmation">
            {t("storage.reset.typeLabel", { word: CONFIRMATION })}
          </Label>
          <Input
            id="factory-reset-confirmation"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
            placeholder={CONFIRMATION}
            autoComplete="off"
            autoFocus
            aria-describedby="factory-reset-hint"
            spellCheck={false}
          />
          <p id="factory-reset-hint" className="text-2xs text-muted-foreground">
            {t("storage.reset.typeHint", { word: CONFIRMATION })}
          </p>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tCommon("actions.cancel")}
          </Button>
          <Button
            variant="destructive"
            disabled={!matches || reset.isPending}
            onClick={() => {
              if (!matches) return;
              reset.mutate(CONFIRMATION, {
                onSuccess: () => {
                  toast.success(t("storage.reset.success"));
                  clearClientCaches();
                  // A full reload is the cleanest way to drop every in-memory
                  // query, the editor and the previously applied appearance.
                  window.location.assign("/");
                },
                onError: (error) => toast.error(errorMessage(error)),
              });
            }}
          >
            {reset.isPending
              ? t("storage.reset.clearing")
              : t("storage.reset.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
