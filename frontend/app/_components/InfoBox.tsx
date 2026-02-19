import React from "react";
import { cn } from "./cn";

type Variant = "info" | "tip" | "warning";

export function InfoBox(props: {
  children: React.ReactNode;
  variant?: Variant;
  title?: string;
  className?: string;
}) {
  const { variant = "info", title, className, children } = props;

  return (
    <div
      className={cn(
        "rounded-xl border p-4 shadow-sm",
        variant === "info" && "border-blue-500/30 bg-blue-500/10 text-blue-900 dark:text-blue-100",
        variant === "tip" && "border-emerald-500/30 bg-emerald-500/10 text-emerald-900 dark:text-emerald-100",
        variant === "warning" && "border-amber-500/30 bg-amber-500/10 text-amber-900 dark:text-amber-100",
        className,
      )}
    >
      {title ? <div className="mb-2 text-sm font-semibold">{title}</div> : null}
      <div className="text-sm leading-relaxed">{children}</div>
    </div>
  );
}
