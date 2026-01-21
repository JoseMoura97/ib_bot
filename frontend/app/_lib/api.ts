import { headers } from "next/headers";

function isAbsoluteUrl(s: string): boolean {
  return /^https?:\/\//i.test(s);
}

function joinPath(base: string, path: string): string {
  const b = base.endsWith("/") ? base.slice(0, -1) : base;
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${b}${p}`;
}

async function buildServerApiUrl(path: string): Promise<string> {
  // Prefer an internal, container-to-container URL for SSR.
  // In docker-compose, set INTERNAL_API_BASE=http://api:8000
  const internalBase = process.env.INTERNAL_API_BASE || process.env.API_INTERNAL_BASE;
  if (internalBase && isAbsoluteUrl(internalBase)) {
    return new URL(path, internalBase).toString();
  }

  // If NEXT_PUBLIC_API_BASE is already absolute, use it.
  const publicBase = process.env.NEXT_PUBLIC_API_BASE || "/api";
  if (isAbsoluteUrl(publicBase)) {
    return joinPath(publicBase, path);
  }

  // Last resort: build absolute URL from request headers.
  // NOTE: this is *not* suitable inside Docker unless the container can reach that host.
  const h = await headers();
  const proto = h.get("x-forwarded-proto") || "http";
  const host = h.get("x-forwarded-host") || h.get("host") || "localhost:8080";
  return `${proto}://${host}${publicBase}${path}`;
}

export async function apiGet<T = unknown>(path: string): Promise<T> {
  const url = await buildServerApiUrl(path);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return (await res.json()) as T;
}

