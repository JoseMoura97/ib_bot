import React from "react";
import { cn } from "../cn";

export function CodeBlock(props: { value: unknown; className?: string }) {
  return (
    <pre className={cn("overflow-auto rounded-lg border bg-muted/40 p-4 text-xs leading-relaxed text-foreground shadow-sm", props.className)}>
      <code>{typeof props.value === "string" ? props.value : JSON.stringify(props.value, null, 2)}</code>
    </pre>
  );
}

