"use client";

import { useEffect, useMemo, useState } from "react";
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
import { useTheme } from "../_components/theme";
import { Card, CardContent } from "../_components/ui/Card";
import { cn } from "../_components/cn";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, TimeScale, Tooltip, Legend);

type EquityPoint = { date: string; value: number };

type RunResultsPayload = {
  run?: { id?: string; type?: string; status?: string };
  portfolio_results?: Array<{
    portfolio_id?: string;
    mode?: string;
    metrics?: Record<string, unknown>;
    artifacts?: {
      equity_curve?: EquityPoint[] | unknown;
      strategy_results?: Record<string, Record<string, unknown>>;
    };
  }>;
  strategy_results?: Array<{
    strategy_name: string;
    metrics?: Record<string, unknown>;
    artifacts?: Record<string, unknown>;
  }>;
};

function coerceEquityCurve(raw: unknown): { x: string; y: number }[] {
  if (!raw) return [];
  if (Array.isArray(raw)) {
    return raw
      .map((row) => {
        if (row && typeof row === "object" && "date" in row && "value" in row) {
          const r = row as { date: string; value: number };
          return { x: r.date, y: Number(r.value) };
        }
        return null;
      })
      .filter(Boolean) as { x: string; y: number }[];
  }
  return [];
}

function pickNum(m: Record<string, unknown> | undefined, ...keys: string[]): number | undefined {
  if (!m) return undefined;
  for (const k of keys) {
    const v = m[k];
    if (typeof v === "number" && Number.isFinite(v)) return v;
  }
  return undefined;
}

function fmtPct(n: number | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

function fmtNum(n: number | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toFixed(digits);
}

type RunPayload = {
  id?: string;
  type?: string;
  status?: string;
  params?: {
    portfolio_name?: string;
    portfolio_description?: string;
    start_date?: string;
    end_date?: string;
    mode?: string;
    transaction_cost_bps?: number;
    strategies?: Array<{ name: string; weight: number }>;
  };
};

type Benchmark = { name?: string; dates: string[]; values: number[] };

export function RunResultsPanel(props: { runId: string | null; runStatus?: string }) {
  const { runId, runStatus } = props;
  const { theme } = useTheme();
  const [results, setResults] = useState<RunResultsPayload | null>(null);
  const [runMeta, setRunMeta] = useState<RunPayload | null>(null);
  const [benchmark, setBenchmark] = useState<Benchmark | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) {
      setResults(null);
      setRunMeta(null);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoadErr(null);
      try {
        const [rrRes, runRes] = await Promise.all([
          fetch(`/api/runs/${encodeURIComponent(runId)}/results`, { cache: "no-store" }),
          fetch(`/api/runs/${encodeURIComponent(runId)}`, { cache: "no-store" }),
        ]);
        if (!rrRes.ok) {
          if (rrRes.status === 404) {
            if (!cancelled) setResults(null);
          } else {
            throw new Error(await rrRes.text());
          }
        } else {
          const data = (await rrRes.json()) as RunResultsPayload;
          if (!cancelled) setResults(data);
        }
        if (runRes.ok) {
          const data = (await runRes.json()) as RunPayload;
          if (!cancelled) setRunMeta(data);
        }
      } catch (e: unknown) {
        if (!cancelled) setLoadErr(String((e as Error)?.message || e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runId, runStatus]);

  // SPY benchmark — fetched once, reused across run selections.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch("/api/plot-data?view=cash", { cache: "no-store" });
        if (!r.ok) return;
        const d = (await r.json()) as { benchmark?: Benchmark };
        if (!cancelled && d.benchmark?.dates?.length) setBenchmark(d.benchmark);
      } catch {
        /* benchmark is optional, fail silently */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const pr = results?.portfolio_results?.[0];
  const metrics = pr?.metrics || {};
  const curve = useMemo(() => coerceEquityCurve(pr?.artifacts?.equity_curve), [pr?.artifacts?.equity_curve]);

  const strategyRows = useMemo(() => {
    const fromArtifacts = pr?.artifacts?.strategy_results;
    if (fromArtifacts && typeof fromArtifacts === "object") {
      return Object.entries(fromArtifacts).map(([name, res]) => {
        const r = res as Record<string, unknown>;
        const err = r.error as string | undefined;
        if (err) {
          return { name, cagr: undefined as number | undefined, sharpe: undefined as number | undefined, sortino: undefined as number | undefined, maxDd: undefined as number | undefined, error: err };
        }
        return {
          name,
          cagr: pickNum(r, "cagr"),
          sharpe: pickNum(r, "sharpe_ratio", "sharpe"),
          sortino: pickNum(r, "sortino_ratio", "sortino"),
          maxDd: pickNum(r, "max_drawdown"),
          error: undefined as string | undefined,
        };
      });
    }
    const sr = results?.strategy_results || [];
    return sr.map((row) => {
      const m = row.metrics;
      const status = m && typeof m.status === "string" ? m.status : "";
      return {
        name: row.strategy_name,
        cagr: pickNum(m, "cagr"),
        sharpe: pickNum(m, "sharpe_ratio", "sharpe"),
        sortino: pickNum(m, "sortino_ratio", "sortino"),
        maxDd: pickNum(m, "max_drawdown"),
        error: status === "ERROR" ? String(m && typeof m.error === "string" ? m.error : "error") : undefined,
      };
    });
  }, [pr?.artifacts?.strategy_results, results?.strategy_results]);

  const chartData = useMemo(() => {
    const datasets: Array<Record<string, unknown>> = [
      {
        label: runMeta?.params?.portfolio_name || "Portfolio equity",
        data: curve.map((p) => ({ x: p.x, y: p.y })),
        borderColor: "#7aa2f7",
        backgroundColor: "transparent",
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.1,
      },
    ];

    // Overlay SPY rescaled so it starts at the same $ value as the portfolio.
    // Lets the user eyeball "did we beat SPY?" without doing the mental math.
    if (benchmark && curve.length > 1) {
      const startStr = curve[0].x;
      const startTs = new Date(startStr).getTime();
      let spyStart: number | null = null;
      const spyPoints: { x: string; y: number }[] = [];
      for (let i = 0; i < benchmark.dates.length; i++) {
        const d = benchmark.dates[i];
        const v = benchmark.values[i];
        if (!Number.isFinite(v)) continue;
        const ts = new Date(d).getTime();
        if (ts < startTs) continue;
        if (spyStart == null) spyStart = v;
        spyPoints.push({ x: d, y: v });
      }
      if (spyStart && spyPoints.length > 1) {
        const scale = (curve[0].y || 1) / spyStart;
        datasets.push({
          label: "SPY (rescaled)",
          data: spyPoints.map((p) => ({ x: p.x, y: p.y * scale })),
          borderColor: "#9fb0c0",
          backgroundColor: "transparent",
          borderWidth: 2,
          borderDash: [5, 5],
          pointRadius: 0,
          tension: 0.1,
        });
      }
    }

    return { datasets };
  }, [curve, benchmark, runMeta?.params?.portfolio_name]);

  const chartOptions = useMemo(() => {
    const isDark = theme === "dark";
    const grid = isDark ? "rgba(148,163,184,0.18)" : "rgba(15,23,42,0.12)";
    const tick = isDark ? "rgba(226,232,240,0.92)" : "rgba(30,41,59,0.9)";
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index" as const, intersect: false },
      plugins: {
        legend: { labels: { color: tick } },
        tooltip: {
          callbacks: {
            label: (ctx: { dataset?: { label?: string }; parsed?: { y?: number } }) =>
              `${ctx.dataset?.label ?? ""}: $${Number(ctx.parsed?.y).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
          },
        },
      },
      scales: {
        x: {
          type: "time" as const,
          time: { unit: "month" as const },
          ticks: { color: tick },
          grid: { color: grid },
        },
        y: {
          ticks: {
            color: tick,
            callback: (v: string | number) => `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
          },
          grid: { color: grid },
        },
      },
    };
  }, [theme]);

  if (!runId) {
    return (
      <Card className="shadow-none">
        <CardContent className="py-10 text-center text-sm text-muted-foreground">Select a run from the list to see equity and metrics.</CardContent>
      </Card>
    );
  }

  const st = (runStatus || "").toUpperCase();
  if (st === "PENDING" || st === "RUNNING") {
    return (
      <Card className="shadow-none">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">Run in progress… results will appear when finished.</CardContent>
      </Card>
    );
  }

  if (loadErr) {
    return (
      <Card className="border-destructive/30 shadow-none">
        <CardContent className="py-4 text-sm text-destructive">{loadErr}</CardContent>
      </Card>
    );
  }

  if (!results || !pr) {
    return (
      <Card className="shadow-none">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          No portfolio results yet (worker may still be writing, or run failed).
        </CardContent>
      </Card>
    );
  }

  const cagr = pickNum(metrics, "cagr");
  const sharpe = pickNum(metrics, "sharpe_ratio", "sharpe");
  const sortino = pickNum(metrics, "sortino_ratio", "sortino");
  const maxDd = pickNum(metrics, "max_drawdown");
  const vol = pickNum(metrics, "volatility", "vol");
  const totalRet = pickNum(metrics, "total_return");
  const finalVal = pickNum(metrics, "final_value");

  // Methodology assumptions (from first strategy result that carries them)
  const anyStrategy = pr?.artifacts?.strategy_results
    ? Object.values(pr.artifacts.strategy_results as Record<string, Record<string, unknown>>)[0]
    : null;
  const costBps = anyStrategy != null ? (anyStrategy.transaction_cost_bps as number | null | undefined) : null;
  const slippageBps = anyStrategy != null ? (anyStrategy.slippage_bps_per_side as number | null | undefined) : null;
  const execOffset = anyStrategy != null ? (anyStrategy.execution_offset_days as number | null | undefined) : null;
  const missingPolicy = anyStrategy != null ? (anyStrategy.missing_ticker_policy as string | null | undefined) : null;
  const hasAssumptions = costBps != null || slippageBps != null || execOffset != null || missingPolicy != null;

  const portfolioName = runMeta?.params?.portfolio_name;
  const portfolioDesc = runMeta?.params?.portfolio_description;
  const strategies = runMeta?.params?.strategies || [];
  const startDate = runMeta?.params?.start_date;
  const endDate = runMeta?.params?.end_date;
  const portfolioCost = runMeta?.params?.transaction_cost_bps;

  return (
    <div className="space-y-4">
      {/* Portfolio identity + window */}
      {(portfolioName || portfolioDesc || startDate) && (
        <Card className="shadow-none">
          <CardContent className="flex flex-wrap items-start justify-between gap-3 py-4">
            <div className="min-w-0">
              {portfolioName ? <div className="text-base font-semibold">{portfolioName}</div> : null}
              {portfolioDesc ? <div className="text-xs text-muted-foreground">{portfolioDesc}</div> : null}
              {(startDate || endDate) && (
                <div className="mt-1 text-xs text-muted-foreground">
                  {startDate} → {endDate || "today"}
                </div>
              )}
            </div>
            {strategies.length > 0 ? (
              <div className="flex flex-wrap gap-1.5 justify-end">
                {strategies.map((s) => (
                  <span
                    key={s.name}
                    className="inline-flex items-center gap-1 rounded-full bg-muted/40 px-2 py-0.5 text-[11px]"
                    title={`Weight: ${(s.weight * 100).toFixed(1)}%`}
                  >
                    <span className="font-medium">{s.name}</span>
                    <span className="font-mono text-muted-foreground">{(s.weight * 100).toFixed(0)}%</span>
                  </span>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>
      )}

      {/* Assumptions row — always visible (was hidden in a <details>) */}
      {(hasAssumptions || portfolioCost != null) && (
        <Card className="shadow-none">
          <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-1 py-3 text-xs">
            <span className="text-muted-foreground">Assumptions:</span>
            {portfolioCost != null && (
              <span className="font-mono">
                <span className="text-muted-foreground">cost </span>
                {portfolioCost} bps
              </span>
            )}
            {slippageBps != null && (
              <span className="font-mono">
                <span className="text-muted-foreground">slippage </span>
                {slippageBps} bps/side
              </span>
            )}
            {execOffset != null && (
              <span className="font-mono">
                <span className="text-muted-foreground">exec lag </span>
                {execOffset}d
              </span>
            )}
            {missingPolicy != null && (
              <span className="font-mono">
                <span className="text-muted-foreground">missing→</span>
                {missingPolicy}
              </span>
            )}
          </CardContent>
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <MetricCard label="CAGR" value={cagr != null ? fmtPct(cagr, 2) : "—"} positive={cagr != null && cagr >= 0} />
        <MetricCard label="Sharpe (rf=2%)" value={fmtNum(sharpe, 2)} />
        <MetricCard label="Sortino (rf=2%)" value={fmtNum(sortino, 2)} />
        <MetricCard label="Max drawdown" value={maxDd != null ? fmtPct(maxDd, 2) : "—"} danger />
        <MetricCard label="Volatility (ann.)" value={vol != null ? fmtPct(vol, 2) : "—"} />
        <MetricCard label="Total return" value={totalRet != null ? fmtPct(totalRet, 2) : "—"} positive={totalRet != null && totalRet >= 0} />
        <MetricCard label="Final value" value={finalVal != null ? `$${finalVal.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "—"} />
      </div>

      {curve.length > 1 ? (
        <Card className="shadow-none">
          <CardContent className="p-4">
            <div className="mb-2 text-sm font-semibold">Equity curve</div>
            <div className="h-[320px]">
              <Line data={chartData as never} options={chartOptions as never} />
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="shadow-none">
          <CardContent className="py-6 text-sm text-muted-foreground">No equity series in results (empty or single point).</CardContent>
        </Card>
      )}

      {strategyRows.length > 0 ? (
        <Card className="shadow-none">
          <CardContent className="p-0">
            <div className="border-b px-4 py-3 text-sm font-semibold">Per-strategy breakdown</div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th className="px-4 py-2 font-medium">Strategy</th>
                    <th className="px-4 py-2 font-medium">CAGR</th>
                    <th className="px-4 py-2 font-medium">Sharpe</th>
                    <th className="px-4 py-2 font-medium">Sortino</th>
                    <th className="px-4 py-2 font-medium">Max DD</th>
                  </tr>
                </thead>
                <tbody>
                  {strategyRows.map((row) => (
                    <tr key={row.name} className="border-b border-border/50">
                      <td className="px-4 py-2 font-medium">{row.name}</td>
                      <td className="px-4 py-2 font-mono text-xs">
                        {row.error ? <span className="text-destructive">{row.error}</span> : row.cagr != null ? fmtPct(row.cagr) : "—"}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs">{row.error ? "—" : fmtNum(row.sharpe)}</td>
                      <td className="px-4 py-2 font-mono text-xs">{row.error ? "—" : fmtNum(row.sortino)}</td>
                      <td className="px-4 py-2 font-mono text-xs">{row.error ? "—" : row.maxDd != null ? fmtPct(row.maxDd) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <details className="rounded-lg border bg-card">
        <summary className="cursor-pointer px-4 py-3 text-xs font-medium text-muted-foreground">Raw JSON (debug)</summary>
        <pre className="max-h-[280px] overflow-auto border-t p-4 text-[11px] leading-relaxed">{JSON.stringify(results, null, 2)}</pre>
      </details>

    </div>
  );
}

function MetricCard(props: { label: string; value: string; positive?: boolean; danger?: boolean }) {
  const { label, value, positive, danger } = props;
  return (
    <Card className="shadow-none">
      <CardContent className="py-4">
        <div className="text-xs font-medium text-muted-foreground">{label}</div>
        <div
          className={cn(
            "mt-1 text-xl font-bold tabular-nums",
            danger && "text-red-600 dark:text-red-400",
            positive === true && "text-emerald-600 dark:text-emerald-400",
            positive === false && "text-red-600 dark:text-red-400",
          )}
        >
          {value}
        </div>
      </CardContent>
    </Card>
  );
}
