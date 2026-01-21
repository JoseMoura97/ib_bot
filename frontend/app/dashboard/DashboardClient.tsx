"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  TimeScale,
  Tooltip,
} from "chart.js";
import "chartjs-adapter-date-fns";
import { Line } from "react-chartjs-2";
import { MetricsTable } from "./MetricsTable";
import { BacktestWizard } from "./BacktestWizard";
import { PageHeader } from "../_components/PageHeader";
import { cn } from "../_components/cn";
import { useTheme } from "../_components/theme";
import { Button } from "../_components/ui/Button";
import { Card, CardContent } from "../_components/ui/Card";
import { Input } from "../_components/ui/Input";
import { Select } from "../_components/ui/Select";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, TimeScale, Tooltip, Legend);

type PlotSeries = {
  name: string;
  dates: string[];
  values: number[];
  cagr?: number;
  sharpe?: number;
  max_drawdown?: number;
};

type PlotData = {
  generated_at: string;
  data_source?: string;
  price_source?: string;
  strategies: Record<string, PlotSeries>;
  benchmark?: PlotSeries;
};

type NormalizationMode = "anchor_to_spy" | "start_at_100";

type StrategyCatalogRow = {
  name: string;
  enabled: boolean;
  config: Record<string, unknown>;
  has_plot: boolean;
  category?: string;
  subcategory?: string;
  description?: string;
  api_status?: string;
  start_date?: string;
};

const COLORS = [
  "#7aa2f7",
  "#bb9af7",
  "#7dcfff",
  "#9ece6a",
  "#e0af68",
  "#f7768e",
  "#ff9e64",
  "#73daca",
  "#b4f9f8",
  "#2ac3de",
  "#c0caf5",
  "#a9b1d6",
  "#9aa5ce",
  "#cfc9c2",
  "#565f89",
];

function getBenchmarkValueAtOrBefore(benchmark: PlotSeries | undefined, dateStr: string): number {
  if (!benchmark || !benchmark.dates?.length || !benchmark.values?.length) return 100;
  const dates = benchmark.dates;
  const values = benchmark.values;

  let lo = 0;
  let hi = dates.length - 1;
  let ans = 0;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (dates[mid] <= dateStr) {
      ans = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return values[ans] ?? values[0] ?? 100;
}

function normalizeSeries(opts: {
  strategy: PlotSeries;
  benchmark?: PlotSeries;
  mode: NormalizationMode;
}): { x: string; y: number }[] {
  const { strategy, benchmark, mode } = opts;
  const dates = strategy.dates || [];
  const values = strategy.values || [];
  if (!dates.length || !values.length) return [];

  const base = values[0] || 100;
  let scale = 1;
  if (mode === "start_at_100") {
    scale = base ? 100 / base : 1;
  } else {
    const spyAtStart = getBenchmarkValueAtOrBefore(benchmark, dates[0]);
    scale = base ? spyAtStart / base : 1;
  }

  return dates.map((d, i) => ({ x: d, y: (values[i] ?? 0) * scale }));
}

function isCongress(name: string) {
  return name.includes("Congress") || name.includes("House") || name.includes("Senate") || name.includes("Committee");
}
function isLobbyingOrContracts(name: string) {
  return name.includes("Lobbying") || name.includes("Contract");
}
function isIndividuals(name: string) {
  return ["Nancy Pelosi", "Dan Meuser", "Josh Gottheimer", "Donald Beyer", "Sheldon Whitehouse"].includes(name);
}
function is13F(name: string) {
  return ["Michael Burry", "Bill Ackman", "Howard Marks", "Bill Gates"].includes(name);
}

export function DashboardClient(props: { onRequestRefresh?: () => Promise<void> }) {
  const { theme } = useTheme();
  const [plotData, setPlotData] = useState<PlotData | null>(null);
  const [catalog, setCatalog] = useState<StrategyCatalogRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [mode, setMode] = useState<NormalizationMode>("anchor_to_spy");
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/plot-data", { cache: "no-store" });
      if (!res.ok) throw new Error(`API error ${res.status}`);
      const data = (await res.json()) as PlotData;
      setPlotData(data);
      // Catalog (best-effort)
      try {
        const cr = await fetch("/api/strategies/catalog", { cache: "no-store" });
        if (cr.ok) {
          const payload = (await cr.json()) as any;
          if (payload && Array.isArray(payload.rows)) setCatalog(payload.rows as StrategyCatalogRow[]);
        }
      } catch {
        // ignore
      }
      // Keep selection; if empty, default to top performer
      const names = Object.keys(data.strategies || {});
      if (names.length && selected.size === 0) {
        // pick best by CAGR if present
        const best = names
          .slice()
          .sort((a, b) => (data.strategies[b]?.cagr ?? -Infinity) - (data.strategies[a]?.cagr ?? -Infinity))[0];
        setSelected(new Set(best ? [best] : []));
      }
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const strategyNames = useMemo(() => {
    const names = Object.keys(plotData?.strategies || {});
    const q = filter.trim().toLowerCase();
    const filtered = q ? names.filter((n) => n.toLowerCase().includes(q)) : names;
    return filtered.sort((a, b) => (plotData?.strategies?.[b]?.cagr ?? -Infinity) - (plotData?.strategies?.[a]?.cagr ?? -Infinity));
  }, [plotData, filter]);

  const chartData = useMemo(() => {
    const benchmark = plotData?.benchmark;
    const datasets: any[] = [];

    if (benchmark) {
      datasets.push({
        label: "SPY (Benchmark)",
        data: benchmark.dates.map((d, i) => ({ x: d, y: benchmark.values[i] })),
        borderColor: "#9fb0c0",
        backgroundColor: "transparent",
        borderWidth: 2,
        borderDash: [5, 5],
        pointRadius: 0,
        tension: 0.1,
      });
    }

    const picked = Array.from(selected);
    picked.forEach((name, idx) => {
      const s = plotData?.strategies?.[name];
      if (!s) return;
      const color = COLORS[idx % COLORS.length];
      datasets.push({
        label: name,
        data: normalizeSeries({ strategy: s, benchmark, mode }),
        borderColor: color,
        backgroundColor: "transparent",
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.1,
      });
    });

    return { datasets };
  }, [plotData, selected, mode]);

  const chartOptions = useMemo(() => {
    const isDark = theme === "dark";
    const grid = isDark ? "rgba(148,163,184,0.18)" : "rgba(15,23,42,0.12)";
    const tick = isDark ? "rgba(226,232,240,0.92)" : "rgba(30,41,59,0.9)";
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index" as const, intersect: false },
      plugins: {
        legend: { position: "top" as const, labels: { color: tick as any } },
        tooltip: {
          callbacks: {
            label: (ctx: any) => `${ctx.dataset.label}: ${Number(ctx.parsed.y).toFixed(2)}`,
          },
        },
      },
      scales: {
        x: {
          type: "time" as const,
          time: { unit: "month" as const },
          ticks: { color: tick as any },
          grid: { color: grid as any },
        },
        y: {
          title: {
            display: true,
            text: mode === "anchor_to_spy" ? "Anchored Value (Strategy starts at SPY)" : "Normalized Value (Start = 100)",
          },
          ticks: { color: tick as any },
          grid: { color: grid as any },
        },
      },
    };
  }, [mode, theme]);

  const stats = useMemo(() => {
    if (!plotData) return null;
    if (selected.size === 0) return null;

    let totalCAGR = 0;
    let totalSharpe = 0;
    let worstDD = 0;
    let bestCAGR = -Infinity;
    let bestName = "";

    selected.forEach((name) => {
      const s = plotData.strategies[name];
      if (!s) return;
      const cagr = s.cagr ?? 0;
      const sharpe = s.sharpe ?? 0;
      const dd = s.max_drawdown ?? 0;
      totalCAGR += cagr;
      totalSharpe += sharpe;
      worstDD = Math.min(worstDD, dd);
      if (cagr > bestCAGR) {
        bestCAGR = cagr;
        bestName = name;
      }
    });

    const n = selected.size || 1;
    return {
      n,
      avgCAGR: totalCAGR / n,
      avgSharpe: totalSharpe / n,
      worstDD,
      bestName,
    };
  }, [plotData, selected]);

  function toggle(name: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  function setPreset(names: string[]) {
    setSelected(new Set(names));
  }

  async function setEnabled(name: string, enabled: boolean) {
    try {
      const res = await fetch(`/api/strategies/${encodeURIComponent(name)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      if (!res.ok) throw new Error(`API error ${res.status}`);
      // Refresh catalog quickly
      const cr = await fetch("/api/strategies/catalog", { cache: "no-store" });
      if (cr.ok) {
        const payload = (await cr.json()) as any;
        if (payload && Array.isArray(payload.rows)) setCatalog(payload.rows as StrategyCatalogRow[]);
      }
    } catch (e: any) {
      setError(String(e?.message || e));
    }
  }

  function presetTop5() {
    if (!plotData) return;
    const names = Object.keys(plotData.strategies || {})
      .sort((a, b) => (plotData.strategies[b]?.cagr ?? -Infinity) - (plotData.strategies[a]?.cagr ?? -Infinity))
      .slice(0, 5);
    setPreset(names);
  }

  function presetCongress() {
    if (catalog) {
      setPreset(catalog.filter((r) => (r.subcategory || "").toLowerCase().includes("congressional") && r.has_plot).map((r) => r.name));
      return;
    }
    if (!plotData) return;
    setPreset(Object.keys(plotData.strategies || {}).filter(isCongress));
  }
  function presetLobbying() {
    if (catalog) {
      setPreset(
        catalog
          .filter((r) => ((r.name || "").includes("Lobbying") || (r.name || "").includes("Contract")) && r.has_plot)
          .map((r) => r.name),
      );
      return;
    }
    if (!plotData) return;
    setPreset(Object.keys(plotData.strategies || {}).filter(isLobbyingOrContracts));
  }
  function presetIndividuals() {
    if (catalog) {
      setPreset(catalog.filter((r) => (r.subcategory || "").toLowerCase().includes("individual") && r.has_plot).map((r) => r.name));
      return;
    }
    if (!plotData) return;
    setPreset(Object.keys(plotData.strategies || {}).filter(isIndividuals));
  }
  function preset13F() {
    if (catalog) {
      setPreset(
        catalog
          .filter((r) => (r.subcategory || "").toLowerCase().includes("hedge") && r.has_plot)
          .map((r) => r.name),
      );
      return;
    }
    if (!plotData) return;
    setPreset(Object.keys(plotData.strategies || {}).filter(is13F));
  }

  async function onRefreshClick() {
    if (props.onRequestRefresh) {
      await props.onRequestRefresh();
    } else {
      await fetch("/api/plot-data/refresh?force=true&max_age_hours=0", { method: "POST" });
    }
  }

  if (loading) return <div className="text-sm text-muted-foreground">Loading plot data…</div>;
  if (error)
    return (
      <Card className="border-destructive/30 bg-destructive/10 shadow-none">
        <CardContent className="py-4 text-sm text-destructive">Error: {error}</CardContent>
      </Card>
    );
  if (!plotData) return <div className="text-sm text-muted-foreground">No data</div>;

  const enabledMissing = (catalog || []).filter((r) => r.enabled && !r.has_plot);
  const enabledCount = (catalog || []).filter((r) => r.enabled).length;
  const disabledWithPlot = (catalog || []).filter((r) => !r.enabled && r.has_plot);

  const subline = `Data: ${plotData.data_source || "unknown"} · Price: ${plotData.price_source || "unknown"} · Updated: ${
    plotData.generated_at ? new Date(plotData.generated_at).toLocaleString() : "unknown"
  }`;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description={subline}
        right={
          <div className="flex flex-wrap items-center gap-2">
            <Select value={mode} onChange={(e) => setMode(e.target.value as NormalizationMode)} className="w-auto">
              <option value="anchor_to_spy">Anchor to SPY at start</option>
              <option value="start_at_100">Normalize start to 100</option>
            </Select>
            <Button onClick={() => load()} size="sm" variant="outline">
              Reload
            </Button>
            <Button onClick={() => onRefreshClick()} size="sm" variant="secondary">
              Refresh plot data
            </Button>
            <Link href="/dashboard/legacy" className="text-sm text-muted-foreground hover:text-foreground">
              Legacy
            </Link>
          </div>
        }
      />

      <Card className="shadow-none">
        <CardContent className="p-4">
          <BacktestWizard
            strategies={
              catalog
                ? catalog
                    .filter((r) => r.has_plot)
                    .map((r) => ({ name: r.name, category: r.category, subcategory: r.subcategory, description: r.description }))
                : Object.keys(plotData.strategies || {}).map((name) => ({ name }))
            }
            defaultSelectedNames={Array.from(selected)}
          />
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-2">
        <Button onClick={() => setPreset(Object.keys(plotData.strategies))} size="sm" variant="outline">
          Show all
        </Button>
        <Button onClick={() => presetTop5()} size="sm" variant="outline">
          Top 5 CAGR
        </Button>
        <Button onClick={() => presetCongress()} size="sm" variant="outline">
          Congress
        </Button>
        <Button onClick={() => presetLobbying()} size="sm" variant="outline">
          Lobbying/Contracts
        </Button>
        <Button onClick={() => presetIndividuals()} size="sm" variant="outline">
          Individuals
        </Button>
        <Button onClick={() => preset13F()} size="sm" variant="outline">
          13F
        </Button>
        <Button onClick={() => setSelected(new Set())} size="sm" variant="ghost">
          Hide all
        </Button>
      </div>

      {catalog ? (
        <Card className="shadow-none">
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="text-sm">
                <div className="font-semibold">Strategy status</div>
                <div className="text-xs text-muted-foreground">
                  Enabled in DB: {enabledCount} · Missing curves: {enabledMissing.length}
                </div>
              </div>
              {enabledMissing.length ? (
                <Button onClick={() => onRefreshClick()} size="sm" variant="secondary">
                  Refresh plot data (fill missing)
                </Button>
              ) : null}
            </div>

            {enabledMissing.length ? (
              <div className="space-y-2">
                <div className="text-xs font-semibold text-muted-foreground">Enabled but missing curves</div>
                <div className="flex flex-wrap gap-2">
                  {enabledMissing.slice(0, 30).map((r) => (
                    <span key={r.name} className="rounded-full border bg-background px-2.5 py-1 text-xs">
                      {r.name}
                    </span>
                  ))}
                  {enabledMissing.length > 30 ? (
                    <span className="self-center text-xs text-muted-foreground">+{enabledMissing.length - 30} more</span>
                  ) : null}
                </div>
              </div>
            ) : null}

            {disabledWithPlot.length ? (
              <div className="space-y-2">
                <div className="text-xs font-semibold text-muted-foreground">Disabled (but curves exist)</div>
                <div className="flex flex-wrap gap-2">
                  {disabledWithPlot.slice(0, 12).map((r) => (
                    <Button key={r.name} onClick={() => setEnabled(r.name, true)} size="sm" variant="outline" title="Enable strategy">
                      Enable {r.name}
                    </Button>
                  ))}
                  {disabledWithPlot.length > 12 ? (
                    <span className="self-center text-xs text-muted-foreground">+{disabledWithPlot.length - 12} more</span>
                  ) : null}
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {stats ? (
        <div className="grid gap-3 md:grid-cols-5">
          <Card className="shadow-none">
            <CardContent className="py-4">
              <div className="text-xs font-semibold text-muted-foreground">Strategies</div>
              <div className="mt-1 text-xl font-semibold">{stats.n}</div>
            </CardContent>
          </Card>
          <Card className="shadow-none">
            <CardContent className="py-4">
              <div className="text-xs font-semibold text-muted-foreground">Avg CAGR</div>
              <div className="mt-1 text-xl font-semibold">{stats.avgCAGR.toFixed(1)}%</div>
            </CardContent>
          </Card>
          <Card className="shadow-none">
            <CardContent className="py-4">
              <div className="text-xs font-semibold text-muted-foreground">Avg Sharpe</div>
              <div className="mt-1 text-xl font-semibold">{stats.avgSharpe.toFixed(2)}</div>
            </CardContent>
          </Card>
          <Card className="shadow-none">
            <CardContent className="py-4">
              <div className="text-xs font-semibold text-muted-foreground">Worst MaxDD</div>
              <div className="mt-1 text-xl font-semibold">{(stats.worstDD * 1).toFixed(1)}%</div>
            </CardContent>
          </Card>
          <Card className="shadow-none">
            <CardContent className="py-4">
              <div className="text-xs font-semibold text-muted-foreground">Best performer</div>
              <div className="mt-1 truncate text-sm font-semibold">{stats.bestName}</div>
            </CardContent>
          </Card>
        </div>
      ) : null}

      <Card className="shadow-none">
        <CardContent className="h-[520px] p-4">
          <Line data={chartData as any} options={chartOptions as any} />
        </CardContent>
      </Card>

      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold tracking-tight">Select strategies</h2>
            <p className="text-sm text-muted-foreground">Pick multiple strategies to compare.</p>
          </div>
          <div className="w-full sm:w-80">
            <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter…" />
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {strategyNames.map((name) => {
            const s = plotData.strategies[name];
            const checked = selected.has(name);
            const cat = catalog?.find((r) => r.name === name);
            return (
              <label
                key={name}
                className={cn(
                  "flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition-colors hover:bg-accent/40",
                  checked && "bg-accent",
                )}
              >
                <input type="checkbox" checked={checked} onChange={() => toggle(name)} className="mt-1" />
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold">{name}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    CAGR: {(s.cagr ?? 0).toFixed(1)}% · Sharpe: {(s.sharpe ?? 0).toFixed(2)}
                  </div>
                  {cat?.subcategory ? (
                    <div className="mt-1 truncate text-[11px] text-muted-foreground">
                      {cat.category ? `${cat.category} / ` : ""}
                      {cat.subcategory}
                      {cat.enabled ? " · enabled" : ""}
                    </div>
                  ) : null}
                </div>
              </label>
            );
          })}
        </div>
      </div>

      <MetricsTable />
    </div>
  );
}

