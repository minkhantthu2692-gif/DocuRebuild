import { Archive, CircleAlert, Download, Plus } from "lucide-react";
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
import { EmptyState } from "@/components/ui/empty-state";
import { CenteredSpinner, Spinner } from "@/components/ui/spinner";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import {
  useCreateProjectBackupCopy,
  useDownloadProjectBackupCopy,
  useProjectBackups,
} from "@/hooks/use-projects";
import { saveBlob } from "@/lib/download";
import { formatDateTime, formatFileSize, resolveLocale } from "@/lib/format";

interface LocalBackupsDialogProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Verified backup copies kept on this device. Copies are created only when the
 * user asks, so nothing is written behind their back during normal editing.
 */
export function LocalBackupsDialog({
  projectId,
  open,
  onOpenChange,
}: LocalBackupsDialogProps) {
  const { t, i18n } = useTranslation("workspace");
  const { t: tCommon } = useTranslation("common");
  const locale = resolveLocale(i18n.language);
  const errorMessage = useApiErrorMessage();
  const backups = useProjectBackups(projectId, open);
  const createCopy = useCreateProjectBackupCopy(projectId);
  const downloadCopy = useDownloadProjectBackupCopy();

  const download = (filename: string) => {
    downloadCopy.mutate(
      { projectId, filename },
      {
        onSuccess: ({ blob, filename: savedName }) => {
          saveBlob(blob, savedName);
          toast.success(t("backups.downloaded"));
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{t("backups.title")}</DialogTitle>
          <DialogDescription>{t("backups.description")}</DialogDescription>
        </DialogHeader>

        <div className="mt-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="max-w-sm text-2xs leading-relaxed text-muted-foreground">
              {t("backups.retention")}
            </p>
            <Button
              type="button"
              size="sm"
              disabled={createCopy.isPending}
              onClick={() =>
                createCopy.mutate(undefined, {
                  onSuccess: () => toast.success(t("backups.created")),
                  onError: (error) => toast.error(errorMessage(error)),
                })
              }
            >
              {createCopy.isPending ? <Spinner /> : <Plus />}
              {t("backups.create")}
            </Button>
          </div>

          {backups.isPending ? (
            <CenteredSpinner label={t("backups.loading")} />
          ) : backups.isError ? (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs leading-relaxed text-destructive"
            >
              <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <span>{errorMessage(backups.error)}</span>
            </div>
          ) : backups.data.length === 0 ? (
            <EmptyState
              compact
              icon={Archive}
              title={t("backups.empty")}
              description={t("backups.emptyHint")}
            />
          ) : (
            <ul className="max-h-80 space-y-2 overflow-y-auto pr-1">
              {backups.data.map((copy) => (
                <li
                  key={copy.filename}
                  className="flex items-center justify-between gap-3 rounded-md border border-border/60 bg-muted/20 px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium">{copy.filename}</p>
                    <p className="text-2xs text-muted-foreground">
                      {formatDateTime(copy.created_at, locale)}
                      {" · "}
                      {formatFileSize(copy.byte_size, locale)}
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t("backups.download")}
                    title={t("backups.download")}
                    disabled={downloadCopy.isPending}
                    onClick={() => download(copy.filename)}
                  >
                    {downloadCopy.isPending &&
                    downloadCopy.variables?.filename === copy.filename ? (
                      <Spinner />
                    ) : (
                      <Download />
                    )}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {tCommon("actions.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
