import * as React from "react";

import { cn } from "@/lib/utils";

export type RadioProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, "type" | "size">;

/** Native radio input styled to match `Checkbox`. */
export const Radio = React.forwardRef<HTMLInputElement, RadioProps>(function Radio(
  { className, disabled, ...props },
  ref,
) {
  return (
    <span
      className={cn("relative inline-flex size-4 shrink-0 items-center justify-center", className)}
      data-slot="radio"
    >
      <input
        ref={ref}
        type="radio"
        disabled={disabled}
        className={cn(
          "peer size-4 shrink-0 cursor-pointer appearance-none rounded-pill border border-input bg-background/80 shadow-xs",
          "transition-[background-color,border-color,box-shadow,transform] duration-fast ease-out",
          "enabled:hover:border-primary/70 enabled:hover:bg-primary/5",
          "checked:border-primary checked:bg-background checked:enabled:hover:bg-primary/5",
          "active:enabled:scale-95",
          "focus-ring",
          "disabled:cursor-not-allowed disabled:opacity-45",
        )}
        {...props}
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 m-auto size-2 scale-50 rounded-pill bg-primary opacity-0 transition-[opacity,transform] duration-fast ease-out peer-checked:scale-100 peer-checked:opacity-100"
      />
    </span>
  );
});
Radio.displayName = "Radio";
