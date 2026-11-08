import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "focus-ring inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium transition-colors duration-fast disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-sm hover:bg-primary/90 active:bg-primary/95",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/75 active:bg-secondary/90",
        outline:
          "border border-input bg-background/70 text-foreground shadow-xs hover:bg-accent hover:text-accent-foreground",
        ghost: "text-foreground hover:bg-accent hover:text-accent-foreground",
        subtle: "bg-primary/10 text-primary hover:bg-primary/15",
        destructive:
          "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-control-sm px-2.5 text-xs [&_svg]:size-icon-sm",
        md: "h-control px-3.5 text-sm [&_svg]:size-icon",
        lg: "h-control-lg px-5 text-sm [&_svg]:size-icon",
        icon: "h-control w-control [&_svg]:size-icon",
        "icon-sm": "h-control-sm w-control-sm [&_svg]:size-icon-sm",
        "icon-xs": "h-control-xs w-control-xs rounded-sm [&_svg]:size-3.5",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "md",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  function Button({ className, variant, size, asChild = false, type, ...props }, ref) {
    const Component = asChild ? Slot : "button";
    return (
      <Component
        ref={ref}
        type={asChild ? type : (type ?? "button")}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  },
);
