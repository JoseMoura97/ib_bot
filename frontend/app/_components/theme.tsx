"use client";

import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "ibbot-theme";

type ThemeContextValue = {
  theme: Theme;
  mounted: boolean;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  if (theme === "dark") root.classList.add("dark");
  else root.classList.remove("dark");
}

export function ThemeProvider(props: { children: React.ReactNode; defaultTheme?: Theme }) {
  const [theme, setThemeState] = useState<Theme>(props.defaultTheme ?? "dark");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      // Default to dark if no stored preference
      const t: Theme = stored === "light" ? "light" : "dark";
      setThemeState(t);
      applyTheme(t);
    } catch {
      // ignore
    }
  }, []);

  const value = useMemo<ThemeContextValue>(() => {
    function setTheme(t: Theme) {
      setThemeState(t);
      try {
        localStorage.setItem(STORAGE_KEY, t);
      } catch {
        // ignore
      }
      applyTheme(t);
    }
    function toggleTheme() {
      setTheme(theme === "dark" ? "light" : "dark");
    }

    return { theme, mounted, setTheme, toggleTheme };
  }, [theme]);

  return <ThemeContext.Provider value={value}>{props.children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}

export const themeStorageKey = STORAGE_KEY;

