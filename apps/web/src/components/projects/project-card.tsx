import { FileText, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import type { ProjectSummary } from "@docurebuild/shared-types";

import { DownloadBackupMenuItem } from "@/components/projects/backup-actions";
import { DownloadBackupDialog } from "@/components/projects/download-backup-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { formatRelativeDate, resolveLocale } from "@/lib/format";

interface ProjectCardProps {
  project: ProjectSummary;
  onRename: (project: ProjectSummary) => void;
  onDelete: (project: ProjectSummary) => void;
}

export function ProjectCard({ project, onRename, onDelete }: ProjectCardProps) {
  const { t, i18n } = useTranslation("dashboard");
  const { t: tCommon } = useTranslation("common");
  const locale = resolveLocale(i18n.resolvedLanguage);
  const updatedRelative = formatRelativeDate(project.updated_at, locale);
  const [backupOpen, setBackupOpen] = useState(false);

  return (
    <article className="group relative overflow-hidden rounded-xl border border-border/70 bg-card/70 shadow-sm backdrop-blur-md transition-all duration-base hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md">
      <Link
        to={`/projects/${project.id}`}
        className="focus-ring block rounded-xl p-4 pb-3 outline-none sm:p-5"
        aria-label={`${t("card.open")}: ${project.name}`}
      >
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <FileText className="size-icon" />
          </span>
          <div className="min-w-0 flex-1 pr-7">
            <h3 className="truncate text-sm font-semibold tracking-tight">{project.name}</h3>
            <p className="mt-1 line-clamp-2 min-h-[2rem] text-xs leading-relaxed text-muted-foreground">
              {project.description || t("localNote")}
            </p>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-2 text-2xs text-muted-foreground">
          <span className="rounded-pill bg-muted/80 px-2 py-0.5">{t("projectsCount", { count: project.page_count })}</span>
          <span className="truncate">{t("card.updated", { date: updatedRelative })}</span>
        </div>
      </Link>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon-xs"
            className="absolute right-3 top-3 opacity-70 transition-opacity group-hover:opacity-100"
            aria-label={tCommon("menu.more")}
          >
            <MoreHorizontal />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DownloadBackupMenuItem onOpen={() => setBackupOpen(true)} />
          <DropdownMenuItem onSelect={() => onRename(project)}>
            <Pencil />
            <span>{t("menu.rename")}</span>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem destructive onSelect={() => onDelete(project)}>
            <Trash2 />
            <span>{t("menu.delete")}</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <DownloadBackupDialog
        projectId={project.id}
        open={backupOpen}
        onOpenChange={setBackupOpen}
      />
    </article>
  );
}
