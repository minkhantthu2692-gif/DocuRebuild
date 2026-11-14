import { useEffect, useState } from "react";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useUpdateProject } from "@/hooks/use-projects";

interface RenameProjectDialogProps {
  project: ProjectSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RenameProjectDialog({ project, open, onOpenChange }: RenameProjectDialogProps) {
  const { t } = useTranslation("dashboard");
  const { t: tCommon } = useTranslation("common");
  const updateProject = useUpdateProject(project?.id ?? "");
  const errorMessage = useApiErrorMessage();
  const [name, setName] = useState("");

  useEffect(() => {
    if (open && project) setName(project.name);
  }, [open, project]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("renameDialog.title")}</DialogTitle>
          <DialogDescription>{t("createDialog.description")}</DialogDescription>
        </DialogHeader>
        <form
          className="mt-5 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (!project || !name.trim()) return;
            updateProject.mutate(
              { name: name.trim() },
              {
                onSuccess: () => onOpenChange(false),
                onError: (error) => toast.error(errorMessage(error)),
              },
            );
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="rename-project-name">{t("renameDialog.name")}</Label>
            <Input
              id="rename-project-name"
              value={name}
              autoFocus
              maxLength={160}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {tCommon("actions.cancel")}
            </Button>
            <Button type="submit" disabled={!name.trim() || updateProject.isPending}>
              {updateProject.isPending ? t("renameDialog.saving") : t("renameDialog.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
