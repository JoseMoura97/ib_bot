"use client";

import { useState } from "react";
import { cn } from "./cn";

export function HelpTooltip(props: { content: string; className?: string }) {
  const [show, setShow] = useState(false);

  return (
    <div className="relative inline-block">
      <button
        type="button"
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        onFocus={() => setShow(true)}
        onBlur={() => setShow(false)}
        className={cn(
          "inline-flex h-4 w-4 items-center justify-center rounded-full border border-muted-foreground/30 text-[10px] text-muted-foreground transition-colors hover:border-muted-foreground hover:bg-muted",
          props.className,
        )}
        aria-label="Help"
      >
        ?
      </button>
      {show ? (
        <div className="absolute bottom-full left-1/2 z-50 mb-2 w-64 -translate-x-1/2 rounded-lg border bg-popover p-3 text-xs leading-relaxed text-popover-foreground shadow-lg">
          {props.content}
          <div className="absolute left-1/2 top-full -translate-x-1/2">
            <div className="border-l-8 border-r-8 border-t-8 border-l-transparent border-r-transparent border-t-popover" />
          </div>
        </div>
      ) : null}
    </div>
  );
}
