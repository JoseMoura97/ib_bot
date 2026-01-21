import React from "react";
import { cn } from "../cn";

export function TableWrap(props: React.HTMLAttributes<HTMLDivElement>) {
  const { className, ...rest } = props;
  return <div className={cn("overflow-x-auto rounded-xl border", className)} {...rest} />;
}

export function Table(props: React.TableHTMLAttributes<HTMLTableElement>) {
  const { className, ...rest } = props;
  return <table className={cn("w-full border-collapse text-sm", className)} {...rest} />;
}

export function Th(props: React.ThHTMLAttributes<HTMLTableCellElement>) {
  const { className, ...rest } = props;
  return (
    <th
      className={cn(
        "sticky top-0 z-10 border-b bg-background/90 px-3 py-2 text-left text-xs font-semibold text-muted-foreground backdrop-blur",
        className,
      )}
      {...rest}
    />
  );
}

export function Td(props: React.TdHTMLAttributes<HTMLTableCellElement>) {
  const { className, ...rest } = props;
  return <td className={cn("border-b px-3 py-2 align-top", className)} {...rest} />;
}

