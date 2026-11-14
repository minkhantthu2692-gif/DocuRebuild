import { Download, KeyRound } from "lucide-react";
import { useId, useState } from "react";
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
import { Spinner } from "@/components/ui/spinner";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useDownloadProjectBackup } from "@/hooks/use-projects";
import { saveBlob } from "@/lib/download";

/** Matches the backend's minimum, so the dialog can explain it before sending. */
const MIN_PASSWORD = 8;

interface DownloadBackupDialogProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Download one verified project archive, optionally password-protected. The
 * password lives only in this dialog's state and in the request body: it is never
 * stored, so the dialog states clearly that it cannot be recovered.
 */
export function DownloadBackupDialog({
  projectId,
  open,
  onOpenChange,
}: DownloadBackupDialogProps) {
  const { t } = useTranslation("dashboard");
  const { t: tCommon } = useTranslation("common");
  const errorMessage = useApiErrorMessage();
  const download = useDownloadProjectBackup();
  const passwordId = useId();
  const confirmationId = useId();

  const [protect, setProtect] = useState(false);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setProtect(false);
    setPassword("");
    setConfirmation("");
    setError(null);
  };

  const changeOpen = (next: boolean) => {
    if (!next) reset();
    onOpenChange(next);
  };

  const submit = () => {
    if (download.isPending) return;
    if (protect) {
      if (password.length < MIN_PASSWORD) {
        setError(t("backup.passwordTooShort", { count: MIN_PASSWORD }));
        return;
      }
      if (password !== confirmation) {
        setError(t("backup.passwordMismatch"));
        return;
      }
    }
    setError(null);
    download.mutate(
      { projectId, password: protect ? password : undefined },
      {
        onSuccess: ({ blob, filename }) => {
          saveBlob(blob, filename);
          toast.success(t("backup.downloaded"));
          changeOpen(false);
        },
        onError: (failure) => toast.error(errorMessage(failure)),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Download className="size-icon-sm text-primary" aria-hidden="true" />
            {t("backup.downloadTitle")}
          </DialogTitle>
          <DialogDescription>{t("backup.downloadDescription")}</DialogDescription>
        </DialogHeader>

        <div className="mt-5 space-y-3">
          <label className="flex items-start gap-2 text-xs leading-relaxed">
            <input
              type="checkbox"
              className="mt-0.5 size-3.5 shrink-0 accent-primary"
              checked={protect}
              onChange={(event) => {
                setProtect(event.target.checked);
                setError(null);
              }}
            />
            <span className="flex items-center gap-1.5">
              <KeyRound className="size-icon-sm text-muted-foreground" aria-hidden="true" />
              {t("backup.protectLabel")}
            </span>
          </label>

          {protect ? (
            <div className="space-y-3 rounded-lg border border-border/70 bg-background/40 p-3">
              <div className="space-y-1.5">
                <Label htmlFor={passwordId} className="text-2xs">
                  {t("backup.password")}
                </Label>
                <Input
                  id={passwordId}
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(event) => {
                    setPassword(event.target.value);
                    setError(null);
                  }}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor={confirmationId} className="text-2xs">
                  {t("backup.passwordConfirm")}
                </Label>
                <Input
                  id={confirmationId}
                  type="password"
                  autoComplete="new-password"
                  value={confirmation}
                  onChange={(event) => {
                    setConfirmation(event.target.value);
                    setError(null);
                  }}
                />
              </div>
              <p className="text-2xs leading-relaxed text-muted-foreground">
                {t("backup.passwordHint", { count: MIN_PASSWORD })}
              </p>
            </div>
          ) : null}

          {error ? (
            <p role="alert" className="text-2xs leading-relaxed text-destructive">
              {error}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => changeOpen(false)}>
            {tCommon("actions.cancel")}
          </Button>
          <Button disabled={download.isPending} onClick={submit}>
            {download.isPending ? <Spinner /> : <Download />}
            {download.isPending ? t("backup.downloading") : t("backup.downloadSubmit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
