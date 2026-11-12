import {
  Activity,
  ArrowLeft,
  CircleAlert,
  FileText,
  Image as ImageIcon,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Pencil,
  Trash2,
} from "lucide-react";
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";

import { DeleteProjectDialog } from "@/components/projects/delete-project-dialog";
import { RenameProjectDialog } from "@/components/projects/rename-project-dialog";
import { DownloadBackupMenuItem } from "@/components/projects/backup-actions";
import { EditorPanel } from "@/components/workspace/editor-panel";
import { ProjectActivityDialog } from "@/components/workspace/project-activity-dialog";
import { SourcePanel } from "@/components/workspace/source-panel";
import { WorkspaceActionsProvider } from "@/components/workspace/workspace-actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/ui/empty-state";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Separator } from "@/components/ui/separator";
import { CenteredSpinner } from "@/components/ui/spinner";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useIsDesktop } from "@/hooks/use-breakpoints";
import { useApiErrorMessage } from "@/hooks/use-api-error";
import { useOpenProject, useProject } from "@/hooks/use-projects";
import {
  MAX_SPLIT,
  MIN_SPLIT,
  clampSplit,
  normalizeLayout,
  readWorkspaceLayout,
  writeWorkspaceLayout,
  type WorkspaceLayout,
} from "@/lib/workspace-layout";
import { cn } from "@/lib/utils";

type MobilePanel = "source" | "document";

export function WorkspacePage() {
  const { projectId = "" } = useParams<{ projectId: string }>();
  const { t } = useTranslation("workspace");
  const { t: tCommon } = useTranslation("common");
  const navigate = useNavigate();
  const isDesktop = useIsDesktop();
  const errorMessage = useApiErrorMessage();

  const projectQuery = useProject(projectId);
  const project = projectQuery.data;
  const { mutate: openProject } = useOpenProject(projectId);
  const openedProjectId = useRef<string | null>(null);

  const [layout, setLayout] = useState<WorkspaceLayout>(() => readWorkspaceLayout());
  const layoutRef = useRef(layout);
  layoutRef.current = layout;
  const containerRef = useRef<HTMLDivElement>(null);
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>("source");
  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [activityOpen, setActivityOpen] = useState(false);

  useEffect(() => {
    if (!projectId || openedProjectId.current === projectId) return;
    openedProjectId.current = projectId;
    openProject();
  }, [projectId, openProject]);

  const updateLayout = (patch: Partial<WorkspaceLayout>) => {
    setLayout((current) => {
      const next = normalizeLayout({ ...current, ...patch });
      writeWorkspaceLayout(next);
      return next;
    });
  };

  const startResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    const container = containerRef.current;
    if (!container) return;
    event.preventDefault();

    const rect = container.getBoundingClientRect();
    let latestSplit = layoutRef.current.split;
    const previousCursor = document.body.style.cursor;
    const previousSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const handleMove = (moveEvent: PointerEvent) => {
      latestSplit = clampSplit((moveEvent.clientX - rect.left) / rect.width);
      setLayout((current) => ({ ...current, split: latestSplit }));
    };

    const stop = () => {
      document.removeEventListener("pointermove", handleMove);
      document.removeEventListener("pointerup", stop);
      document.removeEventListener("pointercancel", stop);
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousSelect;
      writeWorkspaceLayout({ ...layoutRef.current, split: latestSplit });
    };

    document.addEventListener("pointermove", handleMove);
    document.addEventListener("pointerup", stop);
    document.addEventListener("pointercancel", stop);
  };

  if (projectQuery.isLoading) {
    return <CenteredSpinner label={t("loading")} />;
  }

  if (!projectQuery.isSuccess || !project) {
    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <EmptyState
          icon={CircleAlert}
          title={t("notFound")}
          description={errorMessage(projectQuery.error)}
          action={
            <Button asChild variant="outline">
              <Link to="/">{t("backToProjects")}</Link>
            </Button>
          }
        />
      </div>
    );
  }

  const bothPanelsVisible = layout.sourceVisible && layout.editorVisible;
  const sourceRendered = isDesktop ? layout.sourceVisible : true;
  const editorRendered = isDesktop ? layout.editorVisible : true;

  return (
    <WorkspaceActionsProvider>
      <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex h-panel shrink-0 items-center gap-1.5 border-b border-border/60 bg-background/40 px-2.5 backdrop-blur-md">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button asChild variant="ghost" size="icon-sm" aria-label={tCommon("actions.back")}>
              <Link to="/">
                <ArrowLeft />
              </Link>
            </Button>
          </TooltipTrigger>
          <TooltipContent>{tCommon("nav.projects")}</TooltipContent>
        </Tooltip>

        <div className="min-w-0">
          <h1 className="truncate text-sm font-semibold leading-tight tracking-tight">
            {project.name}
          </h1>
          <p className="hidden truncate text-2xs leading-tight text-muted-foreground sm:block">
            {project.description || t("localProject")}
          </p>
        </div>

        <Badge
          variant="secondary"
          className="ml-1 shrink-0 font-mono"
          aria-label={tCommon("units.pages", { count: project.page_count })}
        >
          {project.page_count}
        </Badge>

        <div className="ml-auto flex items-center gap-0.5">
          <div className="hidden items-center gap-0.5 lg:flex">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant={layout.sourceVisible ? "secondary" : "ghost"}
                  size="icon-xs"
                  aria-pressed={layout.sourceVisible}
                  aria-label={
                    layout.sourceVisible ? t("panels.collapseLeft") : t("panels.expandLeft")
                  }
                  disabled={!layout.editorVisible}
                  onClick={() => updateLayout({ sourceVisible: !layout.sourceVisible })}
                >
                  {layout.sourceVisible ? <PanelLeftClose /> : <PanelLeftOpen />}
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {layout.sourceVisible ? t("panels.collapseLeft") : t("panels.expandLeft")}
              </TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant={layout.editorVisible ? "secondary" : "ghost"}
                  size="icon-xs"
                  aria-pressed={layout.editorVisible}
                  aria-label={
                    layout.editorVisible ? t("panels.collapseRight") : t("panels.expandRight")
                  }
                  disabled={!layout.sourceVisible}
                  onClick={() => updateLayout({ editorVisible: !layout.editorVisible })}
                >
                  {layout.editorVisible ? <PanelRightClose /> : <PanelRightOpen />}
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {layout.editorVisible ? t("panels.collapseRight") : t("panels.expandRight")}
              </TooltipContent>
            </Tooltip>
            <Separator orientation="vertical" className="mx-1 h-5" />
          </div>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label={tCommon("menu.more")}>
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => setActivityOpen(true)}>
                <Activity />
                <span>{t("activity.open")}</span>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DownloadBackupMenuItem projectId={projectId} />
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => setRenameOpen(true)}>
                <Pencil />
                <span>{t("projectMenu.rename")}</span>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem destructive onSelect={() => setDeleteOpen(true)}>
                <Trash2 />
                <span>{t("projectMenu.delete")}</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <div className="flex shrink-0 items-center border-b border-border/60 bg-background/30 px-3 py-1.5 lg:hidden">
        <SegmentedControl
          value={mobilePanel}
          onValueChange={(value) => setMobilePanel(value as MobilePanel)}
          label={t("panels.switch")}
          className="max-w-xs"
          options={[
            { value: "source", label: t("source"), icon: <ImageIcon /> },
            { value: "document", label: t("document"), icon: <FileText /> },
          ]}
        />
      </div>

      <div ref={containerRef} className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {sourceRendered ? (
          <div
            className={cn(
              "min-h-0 min-w-0 flex-1 lg:flex-none",
              mobilePanel === "source" ? "flex" : "hidden",
              "lg:flex",
            )}
            style={
              isDesktop && bothPanelsVisible
                ? { width: `${Math.round(layout.split * 100)}%` }
                : undefined
            }
          >
            <SourcePanel
              projectId={projectId}
              className="w-full"
              onContentInserted={() => setMobilePanel("document")}
            />
          </div>
        ) : null}

        {isDesktop && bothPanelsVisible ? (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label={t("panels.resize")}
            aria-valuemin={Math.round(MIN_SPLIT * 100)}
            aria-valuemax={Math.round(MAX_SPLIT * 100)}
            aria-valuenow={Math.round(layout.split * 100)}
            tabIndex={0}
            onPointerDown={startResize}
            onKeyDown={(event) => {
              if (event.key === "ArrowLeft") {
                event.preventDefault();
                updateLayout({ split: layout.split - 0.02 });
              } else if (event.key === "ArrowRight") {
                event.preventDefault();
                updateLayout({ split: layout.split + 0.02 });
              } else if (event.key === "Home") {
                event.preventDefault();
                updateLayout({ split: MIN_SPLIT });
              } else if (event.key === "End") {
                event.preventDefault();
                updateLayout({ split: MAX_SPLIT });
              }
            }}
            className="group hidden w-1.5 shrink-0 cursor-col-resize touch-none items-center justify-center bg-border/30 transition-colors hover:bg-primary/25 focus-visible:bg-primary/25 focus-visible:outline-none lg:flex"
          >
            <span
              className="h-8 w-0.5 rounded-pill bg-border transition-colors group-hover:bg-primary/60"
              aria-hidden="true"
            />
          </div>
        ) : null}

        {editorRendered ? (
          <div
            className={cn(
              "min-h-0 min-w-0 flex-1",
              mobilePanel === "document" ? "flex" : "hidden",
              "lg:flex",
            )}
          >
            <EditorPanel projectId={projectId} className="w-full" />
          </div>
        ) : null}
      </div>

      <RenameProjectDialog
        project={project}
        open={renameOpen}
        onOpenChange={setRenameOpen}
      />
      <DeleteProjectDialog
        project={project}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        onDeleted={() => navigate("/", { replace: true })}
      />
      <ProjectActivityDialog
        projectId={projectId}
        open={activityOpen}
        onOpenChange={setActivityOpen}
      />
      </div>
    </WorkspaceActionsProvider>
  );
}
