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
import { BacktestWizard } from "./BacktestWizard";
import { PageHeader } from "../_components/PageHeader";
import { cn } from "../_components/cn";
import { useTheme } from "../_components/theme";
import { Button } from "../_components/ui/Button";
import { Card, CardContent } from "../_components/ui/Card";
import { Input } from "../_components/ui/Input";
import { Select } from "../_components/ui/Select";
import { HelpTooltip } from "../_components/HelpTooltip";
import { InfoBox } from "../_components/InfoBox";
import { CollapsibleSection } from "../_components/CollapsibleSection";
import { PerformanceBadge } from "../_components/PerformanceBadge";
import { ProgressBar } from "../_components/ProgressBar";

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
  synthetic?: boolean;
  missing?: boolean;
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
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMsg, setRefreshMsg] = useState<string | null>(null);
  const [refreshProgress, setRefreshProgress] = useState<number>(0);
  const [refreshStage, setRefreshStage] = useState<string>("");

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
        legend: { 
          position: "top" as const, 
          labels: { 
            color: tick as any,
            padding: 12,
            font: { size: 12 }
          } 
        },
        tooltip: {
          callbacks: {
            label: (ctx: any) => `${ctx.dataset.label}: $${Number(ctx.parsed.y).toFixed(2)}`,
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
            text: mode === "anchor_to_spy" ? "Portfolio Value (vs S&P 500)" : "Portfolio Value (Normalized)",
          },
          ticks: { 
            color: tick as any,
            callback: (value: any) => `$${Number(value).toFixed(0)}`
          },
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
      setRefreshing(true);
      setRefreshMsg("Queued plot data refresh…");
      setRefreshProgress(0);
      setRefreshStage("queued");
      try {
        const rr = await fetch("/api/plot-data/refresh?force=true&max_age_hours=0", { method: "POST" });
        const payload = (await rr.json().catch(() => ({}))) as any;
        const taskId = payload?.task_id as string | undefined;
        if (!rr.ok) throw new Error(`API error ${rr.status}`);

        // If we got a task id, poll until it finishes (or timeout).
        if (taskId) {
          const startedAt = Date.now();
          while (Date.now() - startedAt < 5 * 60 * 1000) {
            await new Promise((r) => window.setTimeout(r, 1500));
            const sr = await fetch(`/api/plot-data/refresh/${encodeURIComponent(taskId)}`, { cache: "no-store" });
            const st = (await sr.json().catch(() => ({}))) as any;
            const state = String(st?.state || "UNKNOWN");
            const progress = st?.progress as any;
            
            // Update progress bar
            if (progress && typeof progress.percent === "number") {
              setRefreshProgress(progress.percent);
              setRefreshStage(progress.stage || state.toLowerCase());
              
              const stageLabels: Record<string, string> = {
                starting: "Starting...",
                generating: "Generating plot data...",
                validating: "Validating results...",
                complete: "Complete!",
              };
              setRefreshMsg(stageLabels[progress.stage] || `Processing (${state.toLowerCase()})`);
            } else {
              // Fallback for states without progress metadata
              const statePercent: Record<string, number> = {
                PENDING: 5,
                PROGRESS: 50,
                SUCCESS: 100,
              };
              setRefreshProgress(statePercent[state] || 10);
              setRefreshStage(state.toLowerCase());
              setRefreshMsg(`Refreshing plot data… (${state.toLowerCase()})`);
            }
            
            if (state === "SUCCESS") {
              setRefreshProgress(100);
              setRefreshMsg("Plot data refreshed successfully!");
              break;
            }
            if (state === "FAILURE" || state === "REVOKED") {
              setRefreshMsg(`Refresh failed: ${String(st?.detail || "unknown error")}`);
              setRefreshProgress(0);
              break;
            }
          }
        } else {
          setRefreshMsg("Refresh queued.");
        }
      } catch (e: any) {
        setRefreshMsg(null);
        setRefreshProgress(0);
        setError(String(e?.message || e));
      } finally {
        setRefreshing(false);
        // Reload after refresh attempt (successful or not).
        await load();
      }
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
        title="Strategy Dashboard"
        description="Compare historical performance of political and insider trading strategies"
        right={
          <div className="flex flex-wrap items-center gap-2">
            <Link href="/dashboard/guide">
              <Button size="sm" variant="outline">
                User Guide
              </Button>
            </Link>
            <Link href="/dashboard/metrics">
              <Button size="sm" variant="outline">
                Detailed Metrics
              </Button>
            </Link>
            <Button onClick={() => load()} size="sm" variant="outline">
              Reload
            </Button>
            <Button onClick={() => onRefreshClick()} size="sm" variant="secondary" disabled={refreshing}>
              {refreshing ? "Updating…" : "Update Data"}
            </Button>
          </div>
        }
      />

      {refreshing && refreshProgress > 0 ? (
        <Card className="border-blue-500/30 bg-blue-500/10 shadow-none">
          <CardContent className="py-4">
            <ProgressBar value={refreshProgress} label={refreshMsg || "Updating plot data..."} />
          </CardContent>
        </Card>
      ) : null}

      {plotData?.missing || (!plotData?.strategies || Object.keys(plotData.strategies).length === 0) ? (
        <InfoBox variant="warning" title="⚠️ No Plot Data Available">
          <p className="mb-2">
            No strategy data has been generated yet. Click below to fetch real historical prices and generate performance curves.
          </p>
          <Button onClick={() => onRefreshClick()} size="sm" variant="primary" disabled={refreshing}>
            Generate Plot Data
          </Button>
        </InfoBox>
      ) : null}

      <InfoBox variant="tip" title="New here? Start with a preset">
        <p className="mb-2">
          Click one of the preset buttons below to instantly see top-performing strategies. The chart shows how $100 invested would
          have grown over time.
        </p>
        <Link href="/dashboard/guide" className="text-sm font-medium underline">
          Read the full guide →
        </Link>
      </InfoBox>

      <Card className="shadow-none">
        <CardContent className="space-y-3 py-4">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold">Quick Presets</h3>
            <HelpTooltip content="Click a preset to instantly compare popular strategy groups. The chart will update to show their historical performance." />
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            <Button onClick={() => presetTop5()} variant="outline" className="h-auto flex-col items-start gap-1 py-3">
              <span className="font-semibold">Top 5 CAGR</span>
              <span className="text-xs text-muted-foreground">Best historical performers</span>
            </Button>
            <Button onClick={() => presetCongress()} variant="outline" className="h-auto flex-col items-start gap-1 py-3">
              <span className="font-semibold">Congress</span>
              <span className="text-xs text-muted-foreground">House & Senate member trades</span>
            </Button>
            <Button onClick={() => presetIndividuals()} variant="outline" className="h-auto flex-col items-start gap-1 py-3">
              <span className="font-semibold">Individual Politicians</span>
              <span className="text-xs text-muted-foreground">Notable members (Pelosi, etc.)</span>
            </Button>
            <Button onClick={() => presetLobbying()} variant="outline" className="h-auto flex-col items-start gap-1 py-3">
              <span className="font-semibold">Lobbying & Contracts</span>
              <span className="text-xs text-muted-foreground">Companies with gov activity</span>
            </Button>
            <Button onClick={() => preset13F()} variant="outline" className="h-auto flex-col items-start gap-1 py-3">
              <span className="font-semibold">Hedge Funds (13F)</span>
              <span className="text-xs text-muted-foreground">Burry, Ackman, Gates, etc.</span>
            </Button>
            <Button onClick={() => setPreset(Object.keys(plotData.strategies))} variant="outline" className="h-auto flex-col items-start gap-1 py-3">
              <span className="font-semibold">Show All</span>
              <span className="text-xs text-muted-foreground">View every strategy</span>
            </Button>
          </div>
          <div className="flex justify-end">
            <Button onClick={() => setSelected(new Set())} size="sm" variant="ghost">
              Clear selection
            </Button>
          </div>
        </CardContent>
      </Card>

      {catalog && (enabledMissing.length > 0 || disabledWithPlot.length > 0) ? (
        <CollapsibleSection
          title="Strategy Management"
          description={`${enabledCount} enabled · ${enabledMissing.length} missing data`}
          defaultOpen={false}
        >
          {enabledMissing.length ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <div className="text-xs font-semibold text-muted-foreground">Enabled but missing data</div>
                <Button onClick={() => onRefreshClick()} size="sm" variant="secondary" disabled={refreshing}>
                  Update Data
                </Button>
              </div>
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
            <div className="mt-3 space-y-2">
              <div className="text-xs font-semibold text-muted-foreground">Disabled strategies (data available)</div>
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
        </CollapsibleSection>
      ) : null}

      <Card className="shadow-none">
        <CardContent className="space-y-4 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold">Performance Chart</h3>
              <HelpTooltip content="This chart shows how $100 invested in each strategy would have grown over time. The dashed line is the S&P 500 (SPY) benchmark for comparison." />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Select value={mode} onChange={(e) => setMode(e.target.value as NormalizationMode)} className="w-auto">
                <option value="anchor_to_spy">Compare to S&P 500</option>
                <option value="start_at_100">Normalize to 100</option>
              </Select>
            </div>
          </div>
          <div className="h-[700px]">
            <Line data={chartData as any} options={chartOptions as any} />
          </div>
        </CardContent>
      </Card>

      {stats ? (
        <div className="grid gap-3 md:grid-cols-5">
          <Card className="shadow-none">
            <CardContent className="py-4">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
                <span>Strategies</span>
                <HelpTooltip content="Number of strategies currently selected for comparison" />
              </div>
              <div className="mt-1 text-2xl font-bold">{stats.n}</div>
            </CardContent>
          </Card>
          <Card className="shadow-none">
            <CardContent className="py-4">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
                <span>Avg CAGR</span>
                <HelpTooltip content="Average annual return percentage. Higher is better. 15% means your investment grew 15% per year on average." />
              </div>
              <div className={cn("mt-1 text-2xl font-bold", stats.avgCAGR >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400")}>
                {stats.avgCAGR.toFixed(1)}%
              </div>
            </CardContent>
          </Card>
          <Card className="shadow-none">
            <CardContent className="py-4">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
                <span>Avg Sharpe</span>
                <HelpTooltip content="Risk-adjusted return. Higher is better. Above 1.0 is good, above 2.0 is excellent. Shows return per unit of risk." />
              </div>
              <div className="mt-1 text-2xl font-bold">{stats.avgSharpe.toFixed(2)}</div>
            </CardContent>
          </Card>
          <Card className="shadow-none">
            <CardContent className="py-4">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
                <span>Worst Drawdown</span>
                <HelpTooltip content="Largest peak-to-trough decline across selected strategies. Smaller (less negative) is better. -30% means the strategy lost 30% from its peak." />
              </div>
              <div className="mt-1 text-2xl font-bold">{(stats.worstDD * 1).toFixed(1)}%</div>
            </CardContent>
          </Card>
          <Card className="shadow-none">
            <CardContent className="py-4">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
                <span>Best Performer</span>
                <HelpTooltip content="Strategy with the highest CAGR among your current selection" />
              </div>
              <div className="mt-1 truncate text-base font-semibold">{stats.bestName}</div>
            </CardContent>
          </Card>
        </div>
      ) : null}

      <Card className="shadow-none">
        <CardContent className="space-y-3 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold">Browse All Strategies</h3>
              <HelpTooltip content="Click checkboxes to add strategies to the chart. Strategies are sorted by CAGR (best performers first)." />
            </div>
            <div className="w-full sm:w-80">
              <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Search strategies…" />
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
                    checked && "border-primary/50 bg-accent",
                  )}
                >
                  <input type="checkbox" checked={checked} onChange={() => toggle(name)} className="mt-1" />
                  <div className="min-w-0 flex-1">
                    <div className="mb-1.5 flex items-start justify-between gap-2">
                      <div className="truncate text-sm font-semibold">{name}</div>
                      <PerformanceBadge cagr={s.cagr ?? 0} />
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Return: {(s.cagr ?? 0).toFixed(1)}% · Sharpe: {(s.sharpe ?? 0).toFixed(2)}
                    </div>
                    {cat?.subcategory ? (
                      <div className="mt-1.5 truncate text-[11px] text-muted-foreground">
                        {cat.subcategory}
                        {cat.enabled ? " · enabled" : ""}
                      </div>
                    ) : null}
                    {cat?.description ? (
                      <div className="mt-1.5 line-clamp-2 text-[11px] text-muted-foreground">{cat.description}</div>
                    ) : null}
                  </div>
                </label>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <CollapsibleSection
        title="Advanced: Custom Backtest"
        description="Test your own strategy combinations with custom weights and parameters"
        defaultOpen={false}
      >
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
      </CollapsibleSection>

      <div className="flex justify-center">
        <Link href="/dashboard/metrics">
          <Button variant="outline">View Detailed Metrics Comparison</Button>
        </Link>
      </div>
    </div>
  );
}

