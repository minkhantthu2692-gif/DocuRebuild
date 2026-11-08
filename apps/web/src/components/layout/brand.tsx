import { BookOpenText } from "lucide-react";

import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "relative flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gradient-to-br from-primary to-info text-primary-foreground shadow-glow",
        className,
      )}
      aria-hidden="true"
    >
      <BookOpenText className="size-icon-lg" strokeWidth={1.75} />
    </span>
  );
}
