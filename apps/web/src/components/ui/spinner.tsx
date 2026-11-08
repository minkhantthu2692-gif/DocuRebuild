import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("size-icon animate-spin", className)} aria-hidden="true" />;
}

export function CenteredSpinner({ label }: { label?: string }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-3 py-16 text-muted-foreground">
      <Spinner className="size-icon-lg text-primary" />
      {label ? <p className="text-sm">{label}</p> : null}
    </div>
  );
}
