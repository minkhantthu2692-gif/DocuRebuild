import { Plus, Search, TriangleAlert, FolderLock } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import type { ProjectSummary } from "@docurebuild/shared-types";

import { CreateProjectDialog } from "@/components/projects/create-project-dialog";
import { DeleteProjectDialog } from "@/components/projects/delete-project-dialog";
import { ProjectCard } from "@/components/projects/project-card";
import { RenameProjectDialog } from "@/components/projects/rename-project-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useProjects } from "@/hooks/use-projects";

function ProjectGridSkeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="rounded-xl border border-border/60 bg-card/50 p-5">
          <div className="flex gap-3">
            <Skeleton className="size-9 rounded-lg" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-3.5 w-2/3" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-4/5" />
            </div>
          </div>
          <Skeleton className="mt-5 h-4 w-1/2" />
        </div>
      ))}
    </div>
  );
}

export function DashboardPage() {
  const { t } = useTranslation("dashboard");
  const { t: tCommon } = useTranslation("common");
  const projectsQuery = useProjects();
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<ProjectSummary | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ProjectSummary | null>(null);

  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data]);
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return projects;
    return projects.filter(
      (project) =>
        project.name.toLowerCase().includes(query) ||
        project.description.toLowerCase().includes(query),
    );
  }, [projects, search]);

  const hasProjects = projects.length > 0;

  return (
    <div className="scrollbar-thin flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-content px-4 py-7 sm:px-6 lg:py-10">
        <header className="animate-slide-up">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-2xl space-y-2">
              <p className="text-2xs font-semibold uppercase tracking-[0.16em] text-primary">
                {t("eyebrow")}
              </p>
              <h1 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
                {t("title")}
              </h1>
              <p className="max-w-xl text-sm leading-relaxed text-muted-foreground">
                {t("subtitle")}
              </p>
            </div>
            <div className="flex w-full shrink-0 flex-col gap-2 sm:flex-row lg:w-auto">
              <div className="relative w-full sm:w-56">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-icon-sm -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder={t("searchPlaceholder")}
                  className="pl-9"
                  aria-label={t("searchPlaceholder")}
                />
              </div>
              <Button onClick={() => setCreateOpen(true)} className="shrink-0">
                <Plus />
                {tCommon("actions.newProject")}
              </Button>
            </div>
          </div>

          <div className="mt-5 flex items-center gap-2 rounded-lg border border-border/60 bg-background/50 px-3 py-2 text-xs text-muted-foreground">
            <FolderLock className="size-icon-sm shrink-0 text-success" />
            <span>{t("localNote")}</span>
          </div>
        </header>

        <section className="mt-7" aria-labelledby="projects-heading">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <h2 id="projects-heading" className="text-sm font-semibold tracking-tight">
                {t("projects")}
              </h2>
              {hasProjects ? (
                <Badge variant="secondary" className="font-mono">
                  {projects.length}
                </Badge>
              ) : null}
            </div>
            {search.trim() && filtered.length !== projects.length ? (
              <span className="text-2xs text-muted-foreground">
                {t("projectsCount", { count: filtered.length })}
              </span>
            ) : null}
          </div>

          {projectsQuery.isLoading ? <ProjectGridSkeleton /> : null}

          {projectsQuery.isError ? (
            <EmptyState
              icon={TriangleAlert}
              title={t("loadError.title")}
              description={t("loadError.description")}
              action={
                <Button variant="outline" onClick={() => void projectsQuery.refetch()}>
                  {t("loadError.action")}
                </Button>
              }
            />
          ) : null}

          {!projectsQuery.isLoading && !projectsQuery.isError && !hasProjects ? (
            <EmptyState
              icon={FolderLock}
              title={t("empty.title")}
              description={t("empty.description")}
              action={
                <Button onClick={() => setCreateOpen(true)}>
                  <Plus />
                  {t("empty.action")}
                </Button>
              }
            />
          ) : null}

          {!projectsQuery.isLoading && !projectsQuery.isError && hasProjects && filtered.length === 0 ? (
            <EmptyState
              icon={Search}
              title={t("noResults.title")}
              description={t("noResults.description")}
              action={
                <Button variant="outline" onClick={() => setSearch("")}>
                  {t("noResults.action")}
                </Button>
              }
            />
          ) : null}

          {filtered.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {filtered.map((project, index) => (
                <div
                  key={project.id}
                  className="animate-slide-up"
                  style={{ animationDelay: `${Math.min(index, 8) * 35}ms`, animationFillMode: "backwards" }}
                >
                  <ProjectCard
                    project={project}
                    onRename={setRenameTarget}
                    onDelete={setDeleteTarget}
                  />
                </div>
              ))}
            </div>
          ) : null}
        </section>

        <footer className="mt-10 flex flex-wrap items-center gap-x-4 gap-y-1 text-2xs text-muted-foreground">
          <span>{t("phaseNote")}</span>
        </footer>
      </div>

      <CreateProjectDialog open={createOpen} onOpenChange={setCreateOpen} />
      <RenameProjectDialog
        project={renameTarget}
        open={Boolean(renameTarget)}
        onOpenChange={(open) => {
          if (!open) setRenameTarget(null);
        }}
      />
      <DeleteProjectDialog
        project={deleteTarget}
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      />
    </div>
  );
}
