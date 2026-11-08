import { useQuery } from "@tanstack/react-query";
import {
  Check,
  FolderOpen,
  Languages,
  Monitor,
  Moon,
  Plus,
  Settings,
  Sun,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate } from "react-router-dom";

import type { AppearanceSettings } from "@docurebuild/shared-types";

import { CreateProjectDialog } from "@/components/projects/create-project-dialog";
import { BrandMark } from "@/components/layout/brand";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAppSettings, useUpdateSettings } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const THEME_OPTIONS: Array<{
  value: AppearanceSettings["theme"];
  icon: LucideIcon;
}> = [
  { value: "system", icon: Monitor },
  { value: "light", icon: Sun },
  { value: "dark", icon: Moon },
];

export function AppHeader() {
  const { t } = useTranslation("common");
  const { t: tDashboard } = useTranslation("dashboard");
  const { i18n } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [createOpen, setCreateOpen] = useState(false);

  const { data: settings } = useAppSettings();
  const updateSettings = useUpdateSettings();
  const theme = settings?.appearance.theme ?? "system";

  const recentProjects = useQuery({
    queryKey: ["projects"],
    queryFn: api.listProjects,
    staleTime: 20_000,
  });

  const ThemeIcon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;
  const onProjects = location.pathname === "/";

  return (
    <header className="glass-panel z-header flex h-header shrink-0 items-center gap-2 border-x-0 border-t-0 px-2.5 sm:px-4">
      <Link
        to="/"
        className="focus-ring flex shrink-0 items-center gap-2.5 rounded-lg py-1 pr-1"
        aria-label={t("appName")}
      >
        <BrandMark />
        <span className="hidden flex-col leading-none sm:flex">
          <span className="text-[0.95rem] font-semibold tracking-tight">{t("appName")}</span>
          <span className="mt-1 hidden text-2xs text-muted-foreground xl:block">
            {t("tagline")}
          </span>
        </span>
      </Link>

      <nav className="ml-1 flex items-center gap-0.5 sm:ml-3" aria-label={t("nav.projects")}>
        <Button
          asChild
          variant={onProjects ? "secondary" : "ghost"}
          size="sm"
          className={cn("hidden gap-1.5 px-3 sm:inline-flex", onProjects && "shadow-xs")}
        >
          <Link to="/">
            <FolderOpen />
            <span>{t("nav.projects")}</span>
          </Link>
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="gap-1.5 px-2.5 sm:px-3">
              <FolderOpen className="sm:hidden" />
              <span className="hidden sm:inline">{t("actions.open")}</span>
              <span className="sr-only sm:hidden">{t("actions.open")}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-64">
            <DropdownMenuLabel>{t("nav.projects")}</DropdownMenuLabel>
            {recentProjects.isLoading ? (
              <div className="px-2.5 py-2 text-xs text-muted-foreground">{t("loading")}</div>
            ) : null}
            {recentProjects.data?.length ? (
              recentProjects.data.slice(0, 6).map((project) => (
                <DropdownMenuItem
                  key={project.id}
                  onSelect={() => navigate(`/projects/${project.id}`)}
                  className="justify-between"
                >
                  <span className="truncate">{project.name}</span>
                  <span className="shrink-0 text-2xs text-muted-foreground">
                    {project.page_count}
                  </span>
                </DropdownMenuItem>
              ))
            ) : (
              <div className="px-2.5 py-2 text-xs text-muted-foreground">
                {tDashboard("empty.title")}
              </div>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => setCreateOpen(true)}>
              <Plus />
              <span>{t("actions.newProject")}</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <Button
          variant="ghost"
          size="sm"
          className="hidden gap-1.5 px-3 md:inline-flex"
          onClick={() => setCreateOpen(true)}
        >
          <Plus />
          <span>{t("actions.newProject")}</span>
        </Button>
      </nav>

      <div className="ml-auto flex items-center gap-0.5 sm:gap-1">
        <DropdownMenu>
          <Tooltip>
            <TooltipTrigger asChild>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label={t("theme.label")}>
                  <ThemeIcon />
                </Button>
              </DropdownMenuTrigger>
            </TooltipTrigger>
            <TooltipContent>{t("theme.label")}</TooltipContent>
          </Tooltip>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>{t("theme.label")}</DropdownMenuLabel>
            {THEME_OPTIONS.map((option) => {
              const Icon = option.icon;
              return (
                <DropdownMenuItem
                  key={option.value}
                  onSelect={() => updateSettings.mutate({ appearance: { theme: option.value } })}
                  className="justify-between"
                >
                  <span className="flex items-center gap-2">
                    <Icon />
                    {t(`theme.${option.value}`)}
                  </span>
                  {theme === option.value ? <Check className="text-primary" /> : null}
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="gap-1.5 px-2" aria-label={t("language.label")}>
              <Languages className="size-icon-sm" />
              <span className="text-xs font-medium uppercase">
                {i18n.resolvedLanguage === "my" ? "မြ" : "EN"}
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>{t("language.label")}</DropdownMenuLabel>
            {(["en", "my"] as const).map((language) => (
              <DropdownMenuItem
                key={language}
                onSelect={() => updateSettings.mutate({ language })}
                className="justify-between"
              >
                <span>{language === "en" ? t("language.english") : t("language.burmese")}</span>
                {i18n.resolvedLanguage === language ? <Check className="text-primary" /> : null}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button asChild variant="ghost" size="icon-sm" aria-label={t("nav.settings")}>
              <Link to="/settings">
                <Settings />
              </Link>
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t("nav.settings")}</TooltipContent>
        </Tooltip>
      </div>

      <CreateProjectDialog open={createOpen} onOpenChange={setCreateOpen} />
    </header>
  );
}
