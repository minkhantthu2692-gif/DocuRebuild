import { Archive, CircleAlert, Download, Plus, RotateCcw, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type { ProjectBackupSummary } from "@docurebuild/shared-types";

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
  useDeleteProjectBackupCopy,
  useDownloadProjectBackupCopy,
  useProjectBackups,
  useRestoreProjectBackupCopy,
} from "@/hooks/use-projects";
import { saveBlob } from "@/lib/download";
import { formatDateTime, formatFileSize, resolveLocale } from "@/lib/format";

interface LocalBackupsDialogProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Verified backup copies kept on this device. New copies are only written when the
 * user asks or opts into automatic copies in Settings; restoring one always creates
 * a new project and never overwrites current work.
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
  const deleteCopy = useDeleteProjectBackupCopy(projectId);
  const restoreCopy = useRestoreProjectBackupCopy(projectId);
  const [pendingDelete, setPendingDelete] = useState<ProjectBackupSummary | null>(null);
  const [pendingRestore, setPendingRestore] = useState<ProjectBackupSummary | null>(
    null,
  );

  const changeOpen = (next: boolean) => {
    if (!next) {
      setPendingDelete(null);
      setPendingRestore(null);
    }
    onOpenChange(next);
  };

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

  const confirmDelete = () => {
    if (!pendingDelete) return;
    deleteCopy.mutate(pendingDelete.filename, {
      onSuccess: () => {
        toast.success(t("backups.deleted"));
        setPendingDelete(null);
      },
      onError: (error) => toast.error(errorMessage(error)),
    });
  };

  const confirmRestore = () => {
    if (!pendingRestore) return;
    restoreCopy.mutate(pendingRestore.filename, {
      onSuccess: () => {
        toast.success(t("backups.restored"));
        setPendingRestore(null);
      },
      onError: (error) => toast.error(errorMessage(error)),
    });
  };

  return (
    <>
      <Dialog open={open} onOpenChange={changeOpen}>
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
                    <div className="flex items-center gap-1">
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
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        aria-label={t("backups.restoreCopy")}
                        title={t("backups.restoreCopy")}
                        disabled={restoreCopy.isPending}
                        onClick={() => setPendingRestore(copy)}
                      >
                        {restoreCopy.isPending &&
                        restoreCopy.variables === copy.filename ? (
                          <Spinner />
                        ) : (
                          <RotateCcw />
                        )}
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        className="text-muted-foreground hover:text-destructive"
                        aria-label={t("backups.deleteCopy")}
                        title={t("backups.deleteCopy")}
                        disabled={deleteCopy.isPending}
                        onClick={() => setPendingDelete(copy)}
                      >
                        {deleteCopy.isPending &&
                        deleteCopy.variables === copy.filename ? (
                          <Spinner />
                        ) : (
                          <Trash2 />
                        )}
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => changeOpen(false)}>
              {tCommon("actions.close")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={pendingDelete !== null} onOpenChange={(next) => !next && setPendingDelete(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("backups.deleteTitle")}</DialogTitle>
            <DialogDescription>
              {t("backups.deleteDescription", { filename: pendingDelete?.filename ?? "" })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={deleteCopy.isPending}
              onClick={() => setPendingDelete(null)}
            >
              {tCommon("actions.cancel")}
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={deleteCopy.isPending}
              onClick={confirmDelete}
            >
              {deleteCopy.isPending ? <Spinner /> : <Trash2 />}
              {deleteCopy.isPending ? t("backups.deleting") : t("backups.deleteConfirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={pendingRestore !== null}
        onOpenChange={(next) => !next && setPendingRestore(null)}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("backups.restoreTitle")}</DialogTitle>
            <DialogDescription>
              {t("backups.restoreDescription", {
                filename: pendingRestore?.filename ?? "",
              })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={restoreCopy.isPending}
              onClick={() => setPendingRestore(null)}
            >
              {tCommon("actions.cancel")}
            </Button>
            <Button
              type="button"
              disabled={restoreCopy.isPending}
              onClick={confirmRestore}
            >
              {restoreCopy.isPending ? <Spinner /> : <RotateCcw />}
              {restoreCopy.isPending
                ? t("backups.restoring")
                : t("backups.restoreConfirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
