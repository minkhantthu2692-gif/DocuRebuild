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
import { useDeleteProject } from "@/hooks/use-projects";

interface DeleteProjectDialogProps {
  project: ProjectSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted?: () => void;
}

export function DeleteProjectDialog({
  project,
  open,
  onOpenChange,
  onDeleted,
}: DeleteProjectDialogProps) {
  const { t } = useTranslation("dashboard");
  const { t: tCommon } = useTranslation("common");
  const deleteProject = useDeleteProject();
  const errorMessage = useApiErrorMessage();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t("deleteDialog.title", { name: project?.name ?? "" })}
          </DialogTitle>
          <DialogDescription>{t("deleteDialog.description")}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tCommon("actions.cancel")}
          </Button>
          <Button
            variant="destructive"
            disabled={deleteProject.isPending}
            onClick={() => {
              if (!project) return;
              deleteProject.mutate(project.id, {
                onSuccess: () => {
                  toast.success(t("deleteDialog.deleted"));
                  onOpenChange(false);
                  onDeleted?.();
                },
                onError: (error) => toast.error(errorMessage(error)),
              });
            }}
          >
            {deleteProject.isPending ? t("deleteDialog.deleting") : t("deleteDialog.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
