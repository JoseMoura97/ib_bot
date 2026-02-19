"use client";

import { useState } from "react";
import { Card, CardContent } from "./ui/Card";
import { cn } from "./cn";

export function CollapsibleSection(props: {
  title: string;
  description?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(props.defaultOpen ?? false);

  return (
    <Card className={cn("shadow-none", props.className)}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 border-b px-4 py-3 text-left transition-colors hover:bg-accent/40"
      >
        <div className="min-w-0">
          <div className="text-sm font-semibold">{props.title}</div>
          {props.description ? <div className="text-xs text-muted-foreground">{props.description}</div> : null}
        </div>
        <div className="shrink-0 text-muted-foreground transition-transform" style={{ transform: open ? "rotate(180deg)" : "rotate(0deg)" }}>
          ▼
        </div>
      </button>
      {open ? <CardContent className="p-4">{props.children}</CardContent> : null}
    </Card>
  );
}
