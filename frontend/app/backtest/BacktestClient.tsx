"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { PageHeader } from "../_components/PageHeader";
import { Button } from "../_components/ui/Button";
import { Card, CardContent } from "../_components/ui/Card";
import { Input } from "../_components/ui/Input";
import { Badge } from "../_components/ui/Badge";
import { cn } from "../_components/cn";
import { RunResultsPanel } from "./RunResultsPanel";
import type { StrategyCatalogRow } from "../strategies/types";

type StrategyOption = { name: string; category?: string; subcategory?: string; description?: string };

type RunRow = {
  id: string;
  type: string;
  status: string;
  created_at?: string;
  error?: string | null;
  params?: Record<string, unknown>;
};

function todayIso(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function daysAgoIso(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

async function readErrorBody(res: Response): Promise<string> {
  try {
    const txt = await res.text();
    return txt || `HTTP ${res.status}`;
  } catch {
    return `HTTP ${res.status}`;
  }
}

function normalizeWeights(rows: { name: string; weight: number }[]): { name: string; weight: number }[] {
  const sum = rows.reduce((acc, r) => acc + (Number.isFinite(r.weight) ? r.weight : 0), 0);
  if (sum <= 0) return rows.map((r) => ({ ...r, weight: 0 }));
  return rows.map((r) => ({ ...r, weight: r.weight / sum }));
}

function statusBadgeVariant(st: string): "success" | "secondary" | "danger" | "outline" {
  const u = st.toUpperCase();
  if (u === "SUCCESS") return "success";
  if (u === "ERROR") return "danger";
  if (u === "RUNNING" || u === "PENDING") return "secondary";
  return "outline";
}

export function BacktestClient(props: {
  initialCatalog: StrategyCatalogRow[];
  initialRuns: RunRow[];
}) {
  const [catalog, setCatalog] = useState<StrategyCatalogRow[]>(props.initialCatalog || []);
  const [runs, setRuns] = useState<RunRow[]>(props.initialRuns || []);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(props.initialRuns?.[0]?.id ?? null);

  const [filter, setFilter] = useState("");
  const [mode, setMode] = useState<"nav_blend" | "holdings_union">("nav_blend");
  const [startDate, setStartDate] = useState<string>(() => daysAgoIso(365 * 5));
  const [endDate, setEndDate] = useState<string>(() => todayIso());
  const [costBps, setCostBps] = useState<number>(0);
  const [initialCash, setInitialCash] = useState<number>(100000);

  const [selected, setSelected] = useState<{ name: string; weight: number }[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const strategyOptions: StrategyOption[] = useMemo(() => {
    return (catalog || [])
      .filter((r) => r.has_plot)
      .map((r) => ({
        name: r.name,
        category: r.category ?? undefined,
        subcategory: r.subcategory ?? undefined,
        description: r.description ?? undefined,
      }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [catalog]);

  const selectedSet = useMemo(() => new Set(selected.map((s) => s.name)), [selected]);

  const options = useMemo((): StrategyOption[] => {
    const q = filter.trim().toLowerCase();
    const base: StrategyOption[] = strategyOptions.length
      ? strategyOptions
      : catalog.map((r) => ({
          name: r.name,
          category: r.category ?? undefined,
          subcategory: r.subcategory ?? undefined,
          description: r.description ?? undefined,
        }));
    const filtered = q ? base.filter((s) => s.name.toLowerCase().includes(q)) : base;
    return filtered.slice().sort((a, b) => a.name.localeCompare(b.name));
  }, [strategyOptions, catalog, filter]);

  const selectedRun = useMemo(() => runs.find((r) => r.id === selectedRunId) || null, [runs, selectedRunId]);

  const refreshRuns = useCallback(async () => {
    const res = await fetch("/api/runs?limit=20", { cache: "no-store" });
    if (!res.ok) return;
    const rows = (await res.json()) as RunRow[];
    setRuns(rows);
  }, []);

  const refreshCatalog = useCallback(async () => {
    const res = await fetch("/api/strategies/catalog", { cache: "no-store" });
    if (!res.ok) return;
    const payload = (await res.json()) as { rows?: StrategyCatalogRow[] };
    setCatalog(payload.rows || []);
  }, []);

  useEffect(() => {
    if (!selectedRunId) return;
    let cancelled = false;
    let timeoutId = 0;

    async function tick(): Promise<string> {
      try {
        const r = await fetch(`/api/runs/${encodeURIComponent(selectedRunId)}`, { cache: "no-store" });
        if (!r.ok || cancelled) return "";
        const run = (await r.json()) as RunRow;
        setRuns((prev) => {
          const idx = prev.findIndex((x) => x.id === run.id);
          if (idx >= 0) {
            const copy = prev.slice();
            copy[idx] = { ...copy[idx], ...run };
            return copy;
          }
          return [{ ...run, id: String(run.id) }, ...prev];
        });
        const st = (run.status || "").toUpperCase();
        if (st === "SUCCESS" || st === "ERROR") await refreshRuns();
        return st;
      } catch {
        return "";
      }
    }

    async function loop() {
      const st = await tick();
      if (cancelled) return;
      if (st === "PENDING" || st === "RUNNING") {
        timeoutId = window.setTimeout(loop, 1800);
      }
    }

    loop();
    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [selectedRunId, refreshRuns]);

  function showToast(msg: string) {
    setToast(msg);
    window.setTimeout(() => setToast(null), 3000);
  }

  function toggleStrategy(name: string) {
    setSelected((prev) => {
      if (prev.some((r) => r.name === name)) return prev.filter((r) => r.name !== name);
      return [...prev, { name, weight: 1 }];
    });
  }

  function setWeight(name: string, weight: number) {
    setSelected((prev) => prev.map((r) => (r.name === name ? { ...r, weight } : r)));
  }

  function equalizeWeights() {
    setSelected((prev) => {
      const n = prev.length;
      if (!n) return prev;
      const w = 1 / n;
      return prev.map((r) => ({ ...r, weight: w }));
    });
  }

  async function onRun() {
    setErrorMsg(null);
    if (!selected.length) {
      setErrorMsg("Pick at least one strategy.");
      return;
    }
    if (!startDate || !endDate || endDate <= startDate) {
      setErrorMsg("End date must be after start date.");
      return;
    }

    const normalized = normalizeWeights(selected);
    if (normalized.some((r) => !Number.isFinite(r.weight) || r.weight < 0)) {
      setErrorMsg("Weights must be non-negative numbers.");
      return;
    }

    setSubmitting(true);
    try {
      const portfolioName = `Backtest ${new Date().toISOString().slice(0, 19)}`;
      const pr = await fetch("/api/portfolios", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: portfolioName,
          description: "Created from /backtest",
          default_cash: Number(initialCash) || 0,
          settings: { source: "backtest_page" },
        }),
      });
      if (!pr.ok) throw new Error(await readErrorBody(pr));
      const portfolio = (await pr.json()) as { id: string };

      const sr = await fetch(`/api/portfolios/${encodeURIComponent(portfolio.id)}/strategies`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          normalized.map((s) => ({
            strategy_name: s.name,
            enabled: true,
            weight: s.weight,
            overrides: {},
          })),
        ),
      });
      if (!sr.ok) throw new Error(await readErrorBody(sr));

      const rr = await fetch("/api/runs/portfolio-backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          portfolio_id: portfolio.id,
          start_date: startDate,
          end_date: endDate,
          mode,
          transaction_cost_bps: Number(costBps) || 0,
        }),
      });
      if (!rr.ok) throw new Error(await readErrorBody(rr));
      const run = (await rr.json()) as { id: string };

      showToast("Run queued — tracking below.");
      await refreshRuns();
      setSelectedRunId(run.id);
    } catch (e: unknown) {
      setErrorMsg(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Backtest"
        description="Configure a portfolio backtest, launch it, and review equity and risk metrics — without leaving this page."
      />

      {errorMsg ? (
        <Card className="border-destructive/30 bg-destructive/10 shadow-none">
          <CardContent className="py-4 text-sm text-destructive">{errorMsg}</CardContent>
        </Card>
      ) : null}

      {toast ? (
        <div className="fixed bottom-4 right-4 z-[9999] rounded-lg bg-foreground px-3 py-2.5 text-xs text-background shadow-lg">{toast}</div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={() => refreshRuns().catch(() => {})}>
          Refresh runs
        </Button>
        <Button variant="outline" size="sm" onClick={() => refreshCatalog().catch(() => {})}>
          Refresh strategies
        </Button>
        <Link href="/runs" className="inline-flex items-center text-sm text-muted-foreground underline-offset-4 hover:underline">
          All runs (table)
        </Link>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card className="shadow-none">
          <CardContent className="space-y-4 p-4">
            <h2 className="text-base font-semibold">New backtest</h2>

            <label className="grid gap-1.5">
              <span className="text-xs font-medium text-muted-foreground">Blend mode</span>
              <select value={mode} onChange={(e) => setMode(e.target.value as "nav_blend" | "holdings_union")} className="rounded-md border border-input bg-background px-3 py-2 text-sm">
                <option value="nav_blend">Blend returns (recommended)</option>
                <option value="holdings_union">Combine holdings (advanced)</option>
              </select>
            </label>

            <div className="grid grid-cols-2 gap-2">
              <label className="grid gap-1.5">
                <span className="text-xs font-medium text-muted-foreground">Start</span>
                <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </label>
              <label className="grid gap-1.5">
                <span className="text-xs font-medium text-muted-foreground">End</span>
                <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
              </label>
            </div>

            <label className="grid gap-1.5">
              <span className="text-xs font-medium text-muted-foreground">Transaction cost (bps)</span>
              <Input
                type="number"
                value={Number.isFinite(costBps) ? costBps : 0}
                min={0}
                step={0.5}
                onChange={(e) => setCostBps(Number(e.target.value))}
              />
            </label>

            <label className="grid gap-1.5">
              <span className="text-xs font-medium text-muted-foreground">Initial cash (USD)</span>
              <Input
                type="number"
                value={Number.isFinite(initialCash) ? initialCash : 0}
                min={0}
                step={1000}
                onChange={(e) => setInitialCash(Number(e.target.value))}
              />
            </label>

            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={equalizeWeights} disabled={!selected.length}>
                Equalize weights
              </Button>
              <Button variant="primary" onClick={onRun} disabled={submitting}>
                {submitting ? "Starting…" : "Run backtest"}
              </Button>
            </div>

            <div className="rounded-lg border border-border bg-muted/20 p-3">
              <div className="mb-2 text-sm font-medium">Selected ({selected.length})</div>
              {selected.length ? (
                <div className="max-h-[200px] space-y-2 overflow-auto pr-1">
                  {selected.map((s) => (
                    <div key={s.name} className="grid grid-cols-[1fr_100px_auto] items-center gap-2">
                      <div className="min-w-0 truncate text-sm font-medium">{s.name}</div>
                      <Input
                        type="number"
                        className="h-8 text-xs"
                        value={Number.isFinite(s.weight) ? s.weight : 0}
                        min={0}
                        step={0.01}
                        onChange={(e) => setWeight(s.name, Number(e.target.value))}
                      />
                      <Button variant="ghost" size="sm" className="h-8 w-8 p-0" onClick={() => toggleStrategy(s.name)} title="Remove">
                        ×
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">Add strategies from the list below.</p>
              )}
            </div>

            <div>
              <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Search strategies…" className="mb-2" />
              <div className="grid max-h-[280px] grid-cols-1 gap-2 overflow-auto sm:grid-cols-2">
                {options.map((opt) => {
                  const checked = selectedSet.has(opt.name);
                  return (
                    <label
                      key={opt.name}
                      className={cn(
                        "flex cursor-pointer items-start gap-2 rounded-lg border p-2.5 text-sm transition-colors hover:bg-accent/30",
                        checked && "border-primary/50 bg-accent/40",
                      )}
                    >
                      <input type="checkbox" checked={checked} onChange={() => toggleStrategy(opt.name)} className="mt-1" />
                      <div className="min-w-0">
                        <div className="truncate font-semibold">{opt.name}</div>
                        {opt.subcategory || opt.category ? (
                          <div className="text-[11px] text-muted-foreground">{opt.subcategory || opt.category}</div>
                        ) : null}
                        {opt.description ? <div className="mt-1 line-clamp-2 text-[11px] text-muted-foreground">{opt.description}</div> : null}
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card className="shadow-none">
            <CardContent className="p-0">
              <div className="border-b px-4 py-3 text-sm font-semibold">Recent runs</div>
              <div className="max-h-[220px] overflow-auto">
                {runs.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => setSelectedRunId(r.id)}
                    className={cn(
                      "flex w-full items-center justify-between gap-2 border-b px-4 py-2.5 text-left text-sm transition-colors hover:bg-accent/40",
                      r.id === selectedRunId && "bg-accent",
                    )}
                  >
                    <div className="min-w-0">
                      <div className="truncate font-medium">
                        {(r.params as { portfolio_name?: string } | undefined)?.portfolio_name || r.type}
                      </div>
                      <div className="text-[11px] text-muted-foreground">
                        {r.created_at ? new Date(r.created_at).toLocaleString() : r.id.slice(0, 8)}
                      </div>
                    </div>
                    <Badge variant={statusBadgeVariant(r.status)}>{r.status}</Badge>
                  </button>
                ))}
                {!runs.length ? <div className="px-4 py-6 text-sm text-muted-foreground">No runs yet.</div> : null}
              </div>
            </CardContent>
          </Card>

          {selectedRunId ? (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-base font-semibold">Results</h2>
                <Link href={`/runs/${encodeURIComponent(selectedRunId)}`} className="text-xs text-muted-foreground underline-offset-4 hover:underline">
                  Legacy detail page
                </Link>
              </div>
              {selectedRun?.error ? (
                <Card className="border-destructive/30 shadow-none">
                  <CardContent className="py-3 text-sm text-destructive">Run error: {selectedRun.error}</CardContent>
                </Card>
              ) : null}
              <RunResultsPanel runId={selectedRunId} runStatus={selectedRun?.status} />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
