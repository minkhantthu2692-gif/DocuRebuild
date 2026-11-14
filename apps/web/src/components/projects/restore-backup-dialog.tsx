import { ArchiveRestore, CircleAlert, FileArchive, KeyRound, Upload } from "lucide-react";
import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type { ProjectDetail } from "@docurebuild/shared-types";

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
import { useAppMeta } from "@/hooks/use-app";
import { useRestoreProjectBackup } from "@/hooks/use-projects";
import { formatFileSize, resolveLocale } from "@/lib/format";

interface RestoreBackupDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRestored: (project: ProjectDetail) => void;
}

export function RestoreBackupDialog({
  open,
  onOpenChange,
  onRestored,
}: RestoreBackupDialogProps) {
  const { t, i18n } = useTranslation("dashboard");
  const { t: tCommon } = useTranslation("common");
  const locale = resolveLocale(i18n.resolvedLanguage);
  const metaQuery = useAppMeta();
  const restore = useRestoreProjectBackup();
  const errorMessage = useApiErrorMessage();
  const inputRef = useRef<HTMLInputElement>(null);
  const passwordId = useId();

  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [validation, setValidation] = useState<string | null>(null);

  const maxMb = metaQuery.data?.max_backup_mb ?? 2048;

  const reset = () => {
    setFile(null);
    setPassword("");
    setValidation(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) reset();
    onOpenChange(next);
  };

  const choose = (selected: File | null) => {
    setValidation(null);
    if (!selected) {
      setFile(null);
      return;
    }
    if (!/\.(zip|drbz)$/i.test(selected.name)) {
      setFile(null);
      setValidation(t("backup.notZip"));
      return;
    }
    if (selected.size > maxMb * 1024 * 1024) {
      setFile(null);
      setValidation(t("backup.tooLarge", { limit: maxMb }));
      return;
    }
    setFile(selected);
  };

  const submit = () => {
    if (!file || restore.isPending) return;
    restore.mutate(
      { file, password: password || undefined },
      {
        onSuccess: (project) => {
          toast.success(t("backup.success", { name: project.name }));
          handleOpenChange(false);
          onRestored(project);
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ArchiveRestore className="size-icon-sm text-primary" aria-hidden="true" />
            {t("backup.restoreTitle")}
          </DialogTitle>
          <DialogDescription>{t("backup.restoreDescription")}</DialogDescription>
        </DialogHeader>

        <div className="mt-5 space-y-3">
          <input
            ref={inputRef}
            type="file"
            accept=".zip,.drbz,application/zip,application/octet-stream"
            className="sr-only"
            aria-label={t("backup.choose")}
            onChange={(event) => choose(event.target.files?.[0] ?? null)}
          />

          <div className="rounded-lg border border-dashed border-border/80 bg-background/40 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="outline" onClick={() => inputRef.current?.click()}>
                <Upload />
                {t("backup.choose")}
              </Button>
              <span className="text-2xs text-muted-foreground">
                {t("backup.limit", { limit: maxMb })}
              </span>
            </div>

            {file ? (
              <div className="mt-3 flex items-center gap-2 rounded-md border border-border/60 bg-background/60 p-2.5">
                <FileArchive className="size-icon-sm shrink-0 text-primary" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium">{file.name}</p>
                  <p className="text-2xs text-muted-foreground">
                    {formatFileSize(file.size, locale)}
                  </p>
                </div>
              </div>
            ) : (
              <p className="mt-3 text-xs text-muted-foreground">{t("backup.noFile")}</p>
            )}
          </div>

          {validation ? (
            <p
              role="alert"
              className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-2.5 text-2xs leading-relaxed text-destructive"
            >
              <CircleAlert className="mt-0.5 size-icon-sm shrink-0" aria-hidden="true" />
              <span>{validation}</span>
            </p>
          ) : null}

          <div className="space-y-1.5">
            <Label htmlFor={passwordId} className="flex items-center gap-1.5 text-2xs">
              <KeyRound className="size-icon-sm text-muted-foreground" aria-hidden="true" />
              {t("backup.passwordOptional")}
            </Label>
            <Input
              id={passwordId}
              type="password"
              autoComplete="off"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <p className="text-2xs leading-relaxed text-muted-foreground">
              {t("backup.passwordRestoreHint")}
            </p>
          </div>

          <p className="text-2xs leading-relaxed text-muted-foreground">{t("backup.note")}</p>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            {tCommon("actions.cancel")}
          </Button>
          <Button disabled={!file || restore.isPending} onClick={submit}>
            {restore.isPending ? <Spinner /> : <ArchiveRestore />}
            {restore.isPending ? t("backup.restoring") : t("backup.restoreSubmit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
