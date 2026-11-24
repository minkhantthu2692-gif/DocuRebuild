import * as React from "react";

import { cn } from "@/lib/utils";

export type SwitchProps = Omit<
  React.InputHTMLAttributes<HTMLInputElement>,
  "type" | "size"
>;

/**
 * Binary setting switch.
 *
 * A native checkbox with `role="switch"` keeps the familiar label click,
 * keyboard and form behaviour while the track and thumb provide the visual
 * affordance of a toggle. Use it for settings; use `Checkbox` when several
 * items can be selected independently.
 */
export const Switch = React.forwardRef<HTMLInputElement, SwitchProps>(
  function Switch({ className, disabled, ...props }, ref) {
    return (
      <span
        className={cn("relative inline-flex h-5 w-9 shrink-0 items-center", className)}
        data-slot="switch"
      >
        <input
          ref={ref}
          type="checkbox"
          role="switch"
          disabled={disabled}
          className={cn(
            "peer h-5 w-9 cursor-pointer appearance-none rounded-pill border border-transparent bg-muted-foreground/25 shadow-xs",
            "transition-colors duration-base ease-out",
            "enabled:hover:bg-muted-foreground/35",
            "checked:bg-primary checked:enabled:hover:bg-primary/90",
            "focus-ring",
            "disabled:cursor-not-allowed disabled:opacity-45",
          )}
          {...props}
        />
        <span
          aria-hidden="true"
          className={cn(
            "pointer-events-none absolute left-0.5 top-1/2 size-4 -translate-y-1/2 rounded-pill bg-background shadow-sm",
            "transition-transform duration-base ease-out",
            "peer-checked:translate-x-4",
          )}
        />
      </span>
    );
  },
);
Switch.displayName = "Switch";
