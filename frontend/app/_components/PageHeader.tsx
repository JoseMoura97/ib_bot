import React from "react";
import { cn } from "./cn";

export function PageHeader(props: {
  title: string;
  description?: React.ReactNode;
  right?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-3 border-b pb-4 md:flex-row md:items-end md:justify-between", props.className)}>
      <div className="min-w-0">
        <h1 className="truncate text-2xl font-semibold tracking-tight">{props.title}</h1>
        {props.description ? <p className="mt-1 text-sm text-muted-foreground">{props.description}</p> : null}
      </div>
      {props.right ? <div className="flex shrink-0 items-center gap-2">{props.right}</div> : null}
    </div>
  );
}

