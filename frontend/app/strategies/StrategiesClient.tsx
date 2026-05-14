"use client";

import { useMemo, useState, useCallback } from "react";
import { PageHeader } from "../_components/PageHeader";
import { Button } from "../_components/ui/Button";
import { Card, CardContent } from "../_components/ui/Card";
import { Input } from "../_components/ui/Input";
import { Badge } from "../_components/ui/Badge";
import { cn } from "../_components/cn";
import type { StrategyCatalogRow } from "./types";

type SaveState = "idle" | "saving" | "saved" | "error";

function apiStatusVariant(s: string | undefined | null): "success" | "secondary" | "danger" | "outline" {
  const v = (s || "").toLowerCase();
  if (v.includes("ok") || v.includes("live") || v.includes("active")) return "success";
  if (v.includes("error") || v.includes("fail") || v.includes("down")) return "danger";
  return "secondary";
}

/** Recursive editor for strategy config object (no raw JSON). */
function ConfigFieldEditor(props: {
  path: string;
  label: string;
  value: unknown;
  depth: number;
  onChange: (path: string, next: unknown) => void;
}) {
  const { path, label, value, depth, onChange } = props;

  if (value === null || value === undefined) {
    return (
      <div className="grid gap-1.5 rounded-md border border-border/60 bg-muted/20 p-3">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        <span className="text-xs text-muted-foreground">null — use Save to keep or set below</span>
        <Input
          placeholder="Type string or number"
          className="text-sm"
          onBlur={(e) => {
            const t = e.target.value.trim();
            if (!t) return;
            if (t === "true") onChange(path, true);
            else if (t === "false") onChange(path, false);
            else if (!Number.isNaN(Number(t)) && t !== "") onChange(path, Number(t));
            else onChange(path, t);
          }}
        />
      </div>
    );
  }

  if (typeof value === "boolean") {
    return (
      <label className="flex cursor-pointer items-center justify-between gap-3 rounded-md border border-border/60 bg-muted/20 px-3 py-2.5">
        <span className="text-sm font-medium">{label}</span>
        <input
          type="checkbox"
          checked={value}
          onChange={(e) => onChange(path, e.target.checked)}
          className="h-4 w-4"
        />
      </label>
    );
  }

  if (typeof value === "number") {
    return (
      <label className="grid gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        <Input
          type="number"
          value={Number.isFinite(value) ? value : ""}
          onChange={(e) => {
            const n = Number(e.target.value);
            onChange(path, Number.isFinite(n) ? n : 0);
          }}
          className="text-sm"
        />
      </label>
    );
  }

  if (typeof value === "string") {
    return (
      <label className="grid gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        <Input value={value} onChange={(e) => onChange(path, e.target.value)} className="text-sm" />
      </label>
    );
  }

  if (Array.isArray(value)) {
    return (
      <details className="rounded-md border border-border/60 bg-muted/10 p-3" open={depth < 1}>
        <summary className="cursor-pointer text-sm font-medium">{label} (array, {value.length} items)</summary>
        <p className="mt-2 text-xs text-muted-foreground">
          Arrays are shown as JSON for this version — edit carefully or use advanced tools.
        </p>
        <textarea
          className="mt-2 w-full rounded-md border bg-background p-2 font-mono text-xs"
          rows={Math.min(8, Math.max(3, value.length + 2))}
          defaultValue={JSON.stringify(value, null, 2)}
          onBlur={(e) => {
            try {
              const parsed = JSON.parse(e.target.value);
              if (Array.isArray(parsed)) onChange(path, parsed);
            } catch {
              /* keep */
            }
          }}
        />
      </details>
    );
  }

  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    return (
      <details className={cn("rounded-md border border-border/60 bg-muted/10 p-3", depth > 0 && "mt-2")} open={depth < 2}>
        <summary className="cursor-pointer text-sm font-medium">{label}</summary>
        <div className="mt-3 grid gap-3 pl-1">
          {entries.length === 0 ? (
            <span className="text-xs text-muted-foreground">Empty object</span>
          ) : (
            entries.map(([k, v]) => (
              <ConfigFieldEditor
                key={`${path}.${k}`}
                path={`${path}.${k}`}
                label={k}
                value={v}
                depth={depth + 1}
                onChange={onChange}
              />
            ))
          )}
        </div>
      </details>
    );
  }

  return (
    <div className="text-xs text-muted-foreground">
      {label}: unsupported type
    </div>
  );
}

function setDeep(obj: Record<string, unknown>, path: string, next: unknown): Record<string, unknown> {
  const parts = path.split(".").filter(Boolean);
  const out = JSON.parse(JSON.stringify(obj)) as Record<string, unknown>;
  let cur: Record<string, unknown> = out;
  for (let i = 0; i < parts.length - 1; i++) {
    const p = parts[i];
    const child = cur[p];
    if (child && typeof child === "object" && !Array.isArray(child)) {
      cur = child as Record<string, unknown>;
    } else {
      cur[p] = {};
      cur = cur[p] as Record<string, unknown>;
    }
  }
  cur[parts[parts.length - 1]] = next as unknown;
  return out;
}

export function StrategiesClient(props: { initialStrategies: StrategyCatalogRow[] }) {
  const [strategies, setStrategies] = useState<StrategyCatalogRow[]>(props.initialStrategies || []);
  const [filter, setFilter] = useState("");
  const [drawerName, setDrawerName] = useState<string | null>(null);
  const [draftConfig, setDraftConfig] = useState<Record<string, unknown>>({});
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const drawerStrategy = useMemo(
    () => (drawerName ? strategies.find((s) => s.name === drawerName) || null : null),
    [drawerName, strategies],
  );

  const openDrawer = useCallback((name: string) => {
    const s = strategies.find((x) => x.name === name);
    setDrawerName(name);
    setDraftConfig(JSON.parse(JSON.stringify(s?.config ?? {})) as Record<string, unknown>);
    setSaveState("idle");
    setErrorMsg(null);
  }, [strategies]);

  const closeDrawer = useCallback(() => {
    setDrawerName(null);
    setDraftConfig({});
    setSaveState("idle");
  }, []);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return strategies;
    return strategies.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        (s.description || "").toLowerCase().includes(q) ||
        (s.category || "").toLowerCase().includes(q),
    );
  }, [strategies, filter]);

  const grouped = useMemo(() => {
    const m = new Map<string, StrategyCatalogRow[]>();
    for (const s of filtered) {
      const cat = (s.category || "").trim() || "Other";
      if (!m.has(cat)) m.set(cat, []);
      m.get(cat)!.push(s);
    }
    return Array.from(m.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [filtered]);

  async function refresh() {
    const res = await fetch("/api/strategies/catalog", { cache: "no-store" });
    if (!res.ok) throw new Error(`API error ${res.status}`);
    const payload = (await res.json()) as { rows?: StrategyCatalogRow[] };
    const data = (payload?.rows || []) as StrategyCatalogRow[];
    setStrategies(data);
  }

  async function patchStrategy(name: string, patch: Partial<Pick<StrategyCatalogRow, "enabled" | "config">>) {
    const res = await fetch(`/api/strategies/${encodeURIComponent(name)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`API error ${res.status}${txt ? `: ${txt}` : ""}`);
    }
    const updated = (await res.json()) as StrategyCatalogRow;
    setStrategies((prev) => {
      const idx = prev.findIndex((s) => s.name === updated.name);
      if (idx >= 0) {
        const copy = prev.slice();
        copy[idx] = { ...copy[idx], ...updated, config: updated.config || {} };
        return copy;
      }
      return [updated, ...prev].sort((a, b) => a.name.localeCompare(b.name));
    });
    return updated;
  }

  async function onToggleEnabled(name: string, enabled: boolean, e?: React.MouseEvent) {
    e?.stopPropagation();
    setErrorMsg(null);
    try {
      await patchStrategy(name, { enabled });
    } catch (err: unknown) {
      setErrorMsg(String((err as Error)?.message || err));
    }
  }

  function onConfigFieldChange(path: string, next: unknown) {
    setDraftConfig((prev) => setDeep(prev, path, next));
    setSaveState("idle");
  }

  async function onSaveDrawerConfig() {
    if (!drawerStrategy) return;
    setErrorMsg(null);
    setSaveState("saving");
    try {
      const updated = await patchStrategy(drawerStrategy.name, { config: draftConfig });
      setDraftConfig(JSON.parse(JSON.stringify(updated.config ?? {})) as Record<string, unknown>);
      setSaveState("saved");
      window.setTimeout(() => setSaveState("idle"), 2000);
    } catch (err: unknown) {
      setSaveState("error");
      setErrorMsg(String((err as Error)?.message || err));
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Strategies"
        description="Browse by category, toggle strategies on or off, and adjust settings in the side panel — no raw JSON."
      />

      {errorMsg ? (
        <Card className="border-destructive/30 bg-destructive/10 shadow-none">
          <CardContent className="py-4 text-sm text-destructive">{errorMsg}</CardContent>
        </Card>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <div className="w-full max-w-md">
          <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Search by name, description, category…" />
        </div>
        <Button onClick={() => refresh().catch((e) => setErrorMsg(String((e as Error)?.message || e)))} variant="outline">
          Refresh
        </Button>
      </div>

      <div className="text-sm text-muted-foreground">
        {filtered.length} strateg{filtered.length === 1 ? "y" : "ies"} shown
      </div>

      <div className="space-y-8">
        {grouped.map(([category, rows]) => (
          <section key={category}>
            <h2 className="mb-3 text-lg font-semibold tracking-tight">{category}</h2>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {rows.map((s) => (
                <Card
                  key={s.name}
                  role="button"
                  tabIndex={0}
                  onClick={() => openDrawer(s.name)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      openDrawer(s.name);
                    }
                  }}
                  className="cursor-pointer shadow-none transition-colors hover:border-primary/40 hover:bg-accent/30"
                >
                  <CardContent className="flex flex-col gap-3 p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-semibold leading-tight">{s.name}</div>
                        {s.subcategory ? (
                          <div className="mt-0.5 truncate text-xs text-muted-foreground">{s.subcategory}</div>
                        ) : null}
                      </div>
                      <label
                        className="flex shrink-0 items-center gap-2"
                        onClick={(e) => e.stopPropagation()}
                        onKeyDown={(e) => e.stopPropagation()}
                      >
                        <span className="sr-only">Enabled</span>
                        <input
                          type="checkbox"
                          className="h-5 w-5 rounded border"
                          checked={!!s.enabled}
                          onChange={(e) => onToggleEnabled(s.name, e.target.checked)}
                        />
                      </label>
                    </div>
                    {s.description ? (
                      <p className="line-clamp-3 text-xs leading-relaxed text-muted-foreground">{s.description}</p>
                    ) : (
                      <p className="text-xs italic text-muted-foreground">No description</p>
                    )}
                    <div className="mt-auto flex flex-wrap items-center gap-2">
                      {s.api_status ? (
                        <Badge variant={apiStatusVariant(s.api_status)}>{s.api_status}</Badge>
                      ) : (
                        <Badge variant="outline">API n/a</Badge>
                      )}
                      {s.has_plot ? (
                        <Badge variant="success">Plot data</Badge>
                      ) : (
                        <Badge variant="outline">No plot</Badge>
                      )}
                      {s.start_date ? (
                        <span className="text-[10px] text-muted-foreground">from {s.start_date}</span>
                      ) : null}
                    </div>
                    <div className="text-[11px] text-muted-foreground">Click card to edit settings</div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </section>
        ))}
        {filtered.length === 0 ? (
          <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">No strategies match your search.</div>
        ) : null}
      </div>

      {/* Slide-over */}
      {drawerStrategy ? (
        <div className="fixed inset-0 z-50 flex justify-end">
          <button
            type="button"
            className="absolute inset-0 bg-black/40"
            aria-label="Close panel"
            onClick={closeDrawer}
          />
          <div className="relative flex h-full w-full max-w-lg flex-col border-l bg-background shadow-xl animate-in slide-in-from-right duration-200">
            <div className="flex items-start justify-between gap-3 border-b px-4 py-4">
              <div className="min-w-0">
                <div className="truncate text-lg font-semibold">{drawerStrategy.name}</div>
                <div className="mt-1 flex flex-wrap gap-2">
                  <Badge variant={drawerStrategy.enabled ? "success" : "secondary"}>
                    {drawerStrategy.enabled ? "Enabled" : "Disabled"}
                  </Badge>
                  {drawerStrategy.api_status ? (
                    <Badge variant={apiStatusVariant(drawerStrategy.api_status)}>{drawerStrategy.api_status}</Badge>
                  ) : null}
                </div>
              </div>
              <Button variant="ghost" size="sm" onClick={closeDrawer} aria-label="Close">
                ✕
              </Button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
              {drawerStrategy.description ? (
                <p className="mb-4 text-sm text-muted-foreground">{drawerStrategy.description}</p>
              ) : null}
              <div className="mb-4 flex items-center justify-between gap-2">
                <span className="text-sm font-medium">Enabled</span>
                <input
                  type="checkbox"
                  className="h-5 w-5"
                  checked={!!drawerStrategy.enabled}
                  onChange={(e) => onToggleEnabled(drawerStrategy.name, e.target.checked)}
                />
              </div>
              <div className="text-sm font-semibold">Configuration</div>
              <div className="mt-3 space-y-3">
                {Object.keys(draftConfig).length === 0 ? (
                  <p className="text-xs text-muted-foreground">No config keys — defaults in use.</p>
                ) : (
                  Object.entries(draftConfig).map(([k, v]) => (
                    <ConfigFieldEditor key={k} path={k} label={k} value={v} depth={0} onChange={onConfigFieldChange} />
                  ))
                )}
              </div>
            </div>
            <div className="flex items-center justify-between gap-2 border-t px-4 py-3">
              <span className="text-xs text-muted-foreground">
                {saveState === "saved" ? "Saved." : saveState === "error" ? "Fix errors and retry." : ""}
              </span>
              <div className="flex gap-2">
                <Button variant="outline" onClick={closeDrawer}>
                  Close
                </Button>
                <Button variant="primary" onClick={onSaveDrawerConfig} disabled={saveState === "saving"}>
                  {saveState === "saving" ? "Saving…" : "Save settings"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
