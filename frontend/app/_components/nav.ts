export type NavItem = {
  href: string;
  label: string;
  short?: string;
};

export const navItems: NavItem[] = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/strategies", label: "Strategies" },
  { href: "/portfolios", label: "Portfolios" },
  { href: "/allocations", label: "Allocations" },
  { href: "/runs", label: "Runs" },
  { href: "/paper", label: "Paper" },
  { href: "/live", label: "Live" },
];

export function routeTitle(pathname: string): string {
  if (pathname === "/") return "Home";
  const hit = navItems.find((i) => pathname === i.href || pathname.startsWith(`${i.href}/`));
  return hit?.label ?? "IB Bot";
}

