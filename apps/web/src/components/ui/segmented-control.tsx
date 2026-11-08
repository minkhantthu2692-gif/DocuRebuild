import * as ToggleGroupPrimitive from "@radix-ui/react-toggle-group";
import * as React from "react";

import { cn } from "@/lib/utils";

export interface SegmentedOption {
  value: string;
  label: string;
  icon?: React.ReactNode;
  disabled?: boolean;
}

interface SegmentedControlProps {
  value: string;
  onValueChange: (value: string) => void;
  options: SegmentedOption[];
  label: string;
  className?: string;
}

export function SegmentedControl({
  value,
  onValueChange,
  options,
  label,
  className,
}: SegmentedControlProps) {
  return (
    <ToggleGroupPrimitive.Root
      type="single"
      value={value}
      onValueChange={(next) => {
        if (next) onValueChange(next);
      }}
      aria-label={label}
      className={cn(
        "inline-flex w-full items-center gap-0.5 rounded-lg bg-muted/80 p-0.5",
        className,
      )}
    >
      {options.map((option) => (
        <ToggleGroupPrimitive.Item
          key={option.value}
          value={option.value}
          disabled={option.disabled}
          className="focus-ring inline-flex h-control-sm flex-1 items-center justify-center gap-1.5 rounded-md px-2.5 text-xs font-medium text-muted-foreground transition-colors duration-fast hover:text-foreground disabled:pointer-events-none disabled:opacity-50 data-[state=on]:bg-card data-[state=on]:text-foreground data-[state=on]:shadow-xs [&_svg]:size-icon-sm"
        >
          {option.icon}
          <span>{option.label}</span>
        </ToggleGroupPrimitive.Item>
      ))}
    </ToggleGroupPrimitive.Root>
  );
}
