import { cn } from "./cn";

export function ProgressBar(props: {
  value: number; // 0-100
  label?: string;
  className?: string;
  showPercentage?: boolean;
}) {
  const { value, label, className, showPercentage = true } = props;
  const clampedValue = Math.max(0, Math.min(100, value));

  return (
    <div className={cn("space-y-1.5", className)}>
      {(label || showPercentage) && (
        <div className="flex items-center justify-between text-xs">
          {label ? <span className="text-muted-foreground">{label}</span> : <span />}
          {showPercentage ? <span className="font-medium">{clampedValue.toFixed(0)}%</span> : null}
        </div>
      )}
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full bg-primary transition-all duration-300 ease-out"
          style={{ width: `${clampedValue}%` }}
        />
      </div>
    </div>
  );
}
