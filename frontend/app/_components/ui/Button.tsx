import React from "react";
import { cn } from "../cn";

type Variant = "primary" | "secondary" | "ghost" | "outline" | "destructive";
type Size = "sm" | "md" | "lg";

export function Button(
  props: React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: Variant;
    size?: Size;
  },
) {
  const { className, variant = "outline", size = "md", ...rest } = props;
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
        size === "sm" ? "h-8 px-3" : size === "lg" ? "h-11 px-5" : "h-9 px-4",
        variant === "primary"
          ? "bg-primary text-primary-foreground shadow-sm hover:opacity-95"
          : variant === "secondary"
            ? "bg-secondary text-secondary-foreground hover:bg-secondary/80"
            : variant === "ghost"
              ? "hover:bg-accent hover:text-accent-foreground"
              : variant === "destructive"
                ? "bg-destructive text-destructive-foreground shadow-sm hover:opacity-95"
                : "border bg-background shadow-sm hover:bg-accent hover:text-accent-foreground",
        className,
      )}
      {...rest}
    />
  );
}

