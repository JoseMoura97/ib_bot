import { cn } from "./cn";

export function PerformanceBadge(props: { cagr: number; className?: string }) {
  const { cagr, className } = props;

  const variant =
    cagr >= 20
      ? { label: "Excellent", color: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30" }
      : cagr >= 10
        ? { label: "Good", color: "bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-500/30" }
        : cagr >= 0
          ? { label: "Moderate", color: "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30" }
          : { label: "Negative", color: "bg-red-500/15 text-red-700 dark:text-red-300 border-red-500/30" };

  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium", variant.color, className)}>
      {cagr.toFixed(1)}%
    </span>
  );
}
