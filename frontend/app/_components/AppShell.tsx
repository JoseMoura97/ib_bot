"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "./ThemeToggle";
import { cn } from "./cn";
import { navItems, routeTitle } from "./nav";

function AppIcon(props: { className?: string }) {
  return (
    <div
      className={cn(
        "grid h-9 w-9 place-items-center rounded-xl bg-primary text-primary-foreground shadow-sm",
        props.className,
      )}
      aria-hidden
    >
      <span className="text-sm font-semibold tracking-tight">IB</span>
    </div>
  );
}

export function AppShell(props: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const title = routeTitle(pathname);

  return (
    <div className="min-h-dvh bg-background">
      <div className="flex min-h-dvh">
        <aside className="hidden w-64 shrink-0 border-r bg-card/30 md:block">
          <div className="flex h-16 items-center gap-3 px-5">
            <AppIcon />
            <div className="leading-tight">
              <div className="text-sm font-semibold">IB Bot</div>
              <div className="text-xs text-muted-foreground">Control panel</div>
            </div>
          </div>
          <nav className="px-3 pb-4">
            {navItems.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
                    active && "bg-accent text-accent-foreground",
                  )}
                >
                  <span className="h-2 w-2 rounded-full bg-muted-foreground/40" aria-hidden />
                  <span className="truncate">{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-20 border-b bg-background/80 backdrop-blur">
            <div className="container-app flex h-16 items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <Link href="/" className="inline-flex items-center gap-3 no-underline md:hidden">
                  <AppIcon className="h-8 w-8 rounded-lg" />
                  <span className="text-sm font-semibold">IB Bot</span>
                </Link>
                <div className="hidden md:block">
                  <div className="text-sm font-semibold">{title}</div>
                  <div className="text-xs text-muted-foreground">{pathname}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <ThemeToggle />
              </div>
            </div>
          </header>

          <main className="container-app flex-1 py-6">{props.children}</main>
        </div>
      </div>
    </div>
  );
}

