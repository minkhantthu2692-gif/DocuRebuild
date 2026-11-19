import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

interface SettingsSectionProps {
  id: string;
  icon: LucideIcon;
  title: string;
  children: ReactNode;
}

/** One titled card in the settings page, addressable from the side navigation. */
export function SettingsSection({ id, icon: Icon, title, children }: SettingsSectionProps) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-heading`}
      className="glass-panel scroll-mt-24 rounded-xl p-4 shadow-sm sm:p-5"
    >
      <header className="mb-4 flex items-center gap-2">
        <span className="flex size-7 items-center justify-center rounded-md bg-primary/10 text-primary">
          <Icon className="size-icon-sm" aria-hidden="true" />
        </span>
        <h2 id={`${id}-heading`} className="text-sm font-semibold tracking-tight">
          {title}
        </h2>
      </header>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

interface SettingRowProps {
  title: string;
  description?: string;
  children: ReactNode;
  stacked?: boolean;
}

/** A label/description pair beside one control, or above it when stacked. */
export function SettingRow({ title, description, children, stacked = false }: SettingRowProps) {
  return (
    <div
      className={cn(
        "flex gap-2.5",
        stacked ? "flex-col" : "flex-col sm:flex-row sm:items-center sm:justify-between",
      )}
    >
      <div className="min-w-0 max-w-md space-y-0.5">
        <p className="text-sm font-medium leading-snug">{title}</p>
        {description ? (
          <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
        ) : null}
      </div>
      <div className={cn("shrink-0", stacked ? "w-full" : "w-full sm:w-80")}>{children}</div>
    </div>
  );
}
