import React from "react";
import { cn } from "../cn";

type Variant = "default" | "secondary" | "outline" | "success" | "danger";

export function Badge(props: React.HTMLAttributes<HTMLSpanElement> & { variant?: Variant }) {
  const { className, variant = "default", ...rest } = props;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
        variant === "secondary"
          ? "bg-secondary text-secondary-foreground"
          : variant === "outline"
            ? "bg-transparent"
            : variant === "success"
              ? "border-emerald-600/30 bg-emerald-600/10 text-emerald-700 dark:text-emerald-400"
              : variant === "danger"
                ? "border-destructive/30 bg-destructive/10 text-destructive"
                : "bg-primary text-primary-foreground",
        className,
      )}
      {...rest}
    />
  );
}

