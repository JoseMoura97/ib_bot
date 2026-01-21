import "./globals.css";

import { AppShell } from "./_components/AppShell";
import { ThemeProvider, themeStorageKey } from "./_components/theme";

export const metadata = {
  title: "IB Bot",
  description: "IB Bot control panel",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const themeScript = `
(function () {
  try {
    var t = localStorage.getItem(${JSON.stringify(themeStorageKey)});
    if (t !== "dark" && t !== "light") t = "light";
    document.documentElement.dataset.theme = t;
    if (t === "dark") document.documentElement.classList.add("dark");
    else document.documentElement.classList.remove("dark");
  } catch (e) {}
})();`;

  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-dvh">
        <ThemeProvider>
          <AppShell>{children}</AppShell>
        </ThemeProvider>
      </body>
    </html>
  );
}

import "./globals.css";

import type { Metadata } from "next";

import { AppShell } from "./_components/AppShell";
import { ThemeProvider, themeStorageKey } from "./_components/theme";

export const metadata: Metadata = {
  title: "IB Bot",
  description: "IB Bot control panel",
};

export default function RootLayout(props: { children: React.ReactNode }) {
  const themeScript = `
(function () {
  try {
    var t = localStorage.getItem(${JSON.stringify(themeStorageKey)});
    if (t !== "dark" && t !== "light") t = "light";
    document.documentElement.dataset.theme = t;
    if (t === "dark") document.documentElement.classList.add("dark");
    else document.documentElement.classList.remove("dark");
  } catch (e) {}
})();`;

  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-dvh">
        <ThemeProvider>
          <AppShell>{props.children}</AppShell>
        </ThemeProvider>
      </body>
    </html>
  );
}

