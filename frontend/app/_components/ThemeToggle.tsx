"use client";

import { useTheme } from "./theme";
import { cn } from "./cn";

export function ThemeToggle(props: { className?: string }) {
  const { theme, mounted, toggleTheme } = useTheme();

  // Avoid hydration mismatch for label/icon.
  const label = !mounted ? "Theme" : theme === "dark" ? "Dark" : "Light";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={cn(
        "inline-flex items-center gap-2 rounded-md border bg-background px-3 py-2 text-sm font-medium shadow-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        props.className,
      )}
      aria-label="Toggle dark mode"
      title="Toggle theme"
    >
      <span
        className={cn(
          "inline-block h-2.5 w-2.5 rounded-full",
          !mounted ? "bg-muted-foreground" : theme === "dark" ? "bg-foreground" : "bg-muted-foreground",
        )}
      />
      <span className="text-muted-foreground">{label}</span>
    </button>
  );
}

