import { Check, Minus } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

export interface CheckboxProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type" | "size"> {
  /** Shows the mixed state used by "select all" controls. */
  indeterminate?: boolean;
}

/**
 * Native checkbox with a themed indicator.
 *
 * The input stays a real `<input type="checkbox">`, so keyboard support,
 * labelling, form semantics and assistive technology keep working while the
 * visible square is drawn with design tokens.
 */
export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  function Checkbox(
    { className, indeterminate = false, disabled, ...props },
    forwardedRef,
  ) {
    const innerRef = React.useRef<HTMLInputElement>(null);

    React.useImperativeHandle(forwardedRef, () => innerRef.current as HTMLInputElement);

    React.useEffect(() => {
      if (innerRef.current) innerRef.current.indeterminate = indeterminate;
    }, [indeterminate]);

    return (
      <span
        className={cn("relative inline-flex size-4 shrink-0 items-center justify-center", className)}
        data-slot="checkbox"
      >
        <input
          ref={innerRef}
          type="checkbox"
          disabled={disabled}
          className={cn(
            "peer size-4 shrink-0 cursor-pointer appearance-none rounded-xs border border-input bg-background/80 shadow-xs",
            "transition-[background-color,border-color,box-shadow,transform] duration-fast ease-out",
            "enabled:hover:border-primary/70 enabled:hover:bg-primary/5",
            "checked:border-primary checked:bg-primary checked:enabled:hover:bg-primary/90",
            "active:enabled:scale-95",
            "focus-ring",
            "disabled:cursor-not-allowed disabled:opacity-45",
            indeterminate && "border-primary bg-primary",
          )}
          {...props}
        />
        {indeterminate ? (
          <Minus
            aria-hidden="true"
            strokeWidth={3.5}
            className="pointer-events-none absolute inset-0 m-auto size-3 text-primary-foreground"
          />
        ) : (
          <Check
            aria-hidden="true"
            strokeWidth={3.5}
            className="pointer-events-none absolute inset-0 m-auto size-3 scale-75 text-primary-foreground opacity-0 transition-[opacity,transform] duration-fast ease-out peer-checked:scale-100 peer-checked:opacity-100"
          />
        )}
      </span>
    );
  },
);
Checkbox.displayName = "Checkbox";
