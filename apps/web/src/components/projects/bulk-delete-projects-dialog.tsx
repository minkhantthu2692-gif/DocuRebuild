import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type { ProjectSummary } from "@docurebuild/shared-types";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useBulkDeleteProjects } from "@/hooks/use-projects";

interface BulkDeleteProjectsDialogProps {
  projects: ProjectSummary[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted: (deletedIds: string[], failedIds: string[]) => void;
}

const VISIBLE_NAMES = 8;

export function BulkDeleteProjectsDialog({
  projects,
  open,
  onOpenChange,
  onDeleted,
}: BulkDeleteProjectsDialogProps) {
  const { t } = useTranslation("dashboard");
  const { t: tCommon } = useTranslation("common");
  const bulkDelete = useBulkDeleteProjects();
  const errorMessage = useApiErrorMessage();

  const count = projects.length;
  const visible = projects.slice(0, VISIBLE_NAMES);
  const hiddenCount = Math.max(0, count - visible.length);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("bulkDeleteDialog.title", { count })}</DialogTitle>
          <DialogDescription>
            {t("bulkDeleteDialog.description", { count })}
          </DialogDescription>
        </DialogHeader>

        <div className="mt-4 flex gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs leading-relaxed">
          <TriangleAlert
            className="mt-0.5 size-icon-sm shrink-0 text-destructive"
            aria-hidden="true"
          />
          <p>{t("bulkDeleteDialog.warning")}</p>
        </div>

        <div className="mt-4 space-y-1.5">
          <p className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
            {t("bulkDeleteDialog.listLabel")}
          </p>
          <ul className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-border/60 bg-background/40 p-2 text-xs">
            {visible.map((project) => (
              <li key={project.id} className="truncate px-1 py-0.5">
                {project.name}
              </li>
            ))}
          </ul>
          {hiddenCount > 0 ? (
            <p className="text-2xs text-muted-foreground">
              {t("bulkDeleteDialog.more", { count: hiddenCount })}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tCommon("actions.cancel")}
          </Button>
          <Button
            variant="destructive"
            disabled={bulkDelete.isPending || count === 0}
            onClick={() => {
              if (count === 0) return;
              bulkDelete.mutate(
                projects.map((project) => project.id),
                {
                  onSuccess: (result) => {
                    if (result.deleted.length > 0) {
                      toast.success(
                        t("bulkDeleteDialog.deleted", { count: result.deleted.length }),
                      );
                    }
                    if (result.failed.length > 0) {
                      toast.error(
                        t("bulkDeleteDialog.partial", {
                          deleted: result.deleted.length,
                          failed: result.failed.length,
                        }),
                      );
                    }
                    onOpenChange(false);
                    onDeleted(
                      result.deleted,
                      result.failed.map((failure) => failure.id),
                    );
                  },
                  onError: (error) => toast.error(errorMessage(error)),
                },
              );
            }}
          >
            {bulkDelete.isPending
              ? t("bulkDeleteDialog.deleting")
              : t("bulkDeleteDialog.confirm", { count })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
