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
import { useTheme } from "../../_components/theme";
import { Card, CardContent } from "../../_components/ui/Card";
import { Button } from "../../_components/ui/Button";
import { Badge } from "../../_components/ui/Badge";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, TimeScale, Tooltip, Legend);

// Same palette as the dashboard so colours stay consistent across views.
const COLORS = [
  "#7aa2f7",
  "#bb9af7",
  "#9ece6a",
  "#e0af68",
  "#f7768e",
  "#7dcfff",
  "#c0caf5",
  "#73daca",
];

type EquityPoint = { date: string; value: number };

type Run = {
  id: string;
  type: string;
  status: string;
  params?: Record<string, unknown>;
  created_at?: string;
  finished_at?: string | null;
  error?: string | null;
};

type RunResults = {
  run?: { id?: string; type?: string; status?: string };
  portfolio_results?: Array<{
    portfolio_id?: string;
    mode?: string;
    metrics?: Record<string, unknown>;
    artifacts?: {
      equity_curve?: EquityPoint[] | unknown;
    };
  }>;
};

type Loaded = {
  id: string;
  run: Run | null;
  results: RunResults | null;
  label: string;
  error: string | null;
};

function coerceEquityCurve(raw: unknown): { x: string; y: number }[] {
  if (!raw || !Array.isArray(raw)) return [];
  const out: { x: string; y: number }[] = [];
  for (const row of raw) {
    if (row && typeof row === "object" && "date" in row && "value" in row) {
      const r = row as { date: string; value: number };
      const y = Number(r.value);
      if (Number.isFinite(y)) out.push({ x: r.date, y });
    }
  }
  return out;
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

function deriveLabel(run: Run | null, fallbackId: string): string {
  if (!run) return fallbackId.slice(0, 8);
  const params = (run.params || {}) as Record<string, unknown>;
  // Backend-side `Ad hoc backtest` portfolios bake the timestamp into name;
  // prefer portfolio_name if explicit, else strategies count + mode + start.
  const pn = params.portfolio_name;
  if (typeof pn === "string" && pn) return pn;
  const mode = typeof params.mode === "string" ? params.mode : "";
  const start = typeof params.start_date === "string" ? params.start_date : "";
  const strat = Array.isArray(params.strategies) ? (params.strategies as unknown[]).length : 0;
  const bits = [
    `${strat} strat${strat === 1 ? "" : "s"}`,
    mode || null,
    start || null,
  ].filter(Boolean);
  return bits.join(" · ") || fallbackId.slice(0, 8);
}

type NormalizationMode = "start_at_100" | "raw" | "anchor_to_longest";

function normalizeCurve(
  curve: { x: string; y: number }[],
  mode: NormalizationMode,
  anchorAtStart?: number,
): { x: string; y: number }[] {
  if (!curve.length) return [];
  if (mode === "raw") return curve;
  const base = curve[0]?.y;
  if (!base) return curve;
  // anchor_to_longest: scale so this curve starts where the longest curve
  // is at THIS curve's first date. Lets you eyeball "did the shorter
  // portfolio outperform the longer one over its own window?" instead of
  // visually restarting every curve at the same baseline.
  const targetStart = mode === "anchor_to_longest" && anchorAtStart ? anchorAtStart : 100;
  const scale = targetStart / base;
  return curve.map((p) => ({ x: p.x, y: p.y * scale }));
}

// Find the value of `curve` on or before `dateStr`. Used for anchor mode —
// we look up where the longest curve was on the shorter curve's start date.
function valueAtOrBefore(
  curve: { x: string; y: number }[],
  dateStr: string,
): number | undefined {
  if (!curve.length) return undefined;
  const target = new Date(dateStr).getTime();
  let last: number | undefined;
  for (const p of curve) {
    if (new Date(p.x).getTime() > target) break;
    last = p.y;
  }
  return last ?? curve[0].y;
}

export function CompareClient(props: { runIds: string[] }) {
  const { theme } = useTheme();
  const runIds = useMemo(() => Array.from(new Set(props.runIds)), [props.runIds]);
  const [items, setItems] = useState<Loaded[]>([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<NormalizationMode>("start_at_100");

  useEffect(() => {
    let cancelled = false;
    if (runIds.length === 0) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    (async () => {
      const out: Loaded[] = await Promise.all(
        runIds.map(async (id) => {
          try {
            const [runRes, resultsRes] = await Promise.all([
              fetch(`/api/runs/${encodeURIComponent(id)}`, { cache: "no-store" }),
              fetch(`/api/runs/${encodeURIComponent(id)}/results`, { cache: "no-store" }),
            ]);
            const run = runRes.ok ? ((await runRes.json()) as Run) : null;
            const results = resultsRes.ok ? ((await resultsRes.json()) as RunResults) : null;
            return {
              id,
              run,
              results,
              label: deriveLabel(run, id),
              error: run ? null : `Run not found: ${id}`,
            };
          } catch (e: unknown) {
            return {
              id,
              run: null,
              results: null,
              label: id.slice(0, 8),
              error: String((e as Error)?.message || e),
            };
          }
        }),
      );
      if (!cancelled) {
        setItems(out);
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runIds]);

  const chartData = useMemo(() => {
    // Precompute each item's raw curve so anchor mode can look up the longest
    // curve's value at shorter curves' start dates.
    const enriched = items
      .map((it, idx) => {
        const pr = it.results?.portfolio_results?.[0];
        const curve = coerceEquityCurve(pr?.artifacts?.equity_curve);
        return curve.length >= 2 ? { it, idx, curve } : null;
      })
      .filter(Boolean) as Array<{ it: Loaded; idx: number; curve: { x: string; y: number }[] }>;

    // For anchor_to_longest: the "anchor" is the longest curve (start_at_100
    // normalized so the picture is on the same axis as the other modes).
    let anchorCurve: { x: string; y: number }[] | null = null;
    if (mode === "anchor_to_longest" && enriched.length) {
      const longest = enriched.reduce((a, b) => (b.curve.length > a.curve.length ? b : a));
      anchorCurve = normalizeCurve(longest.curve, "start_at_100");
    }

    const datasets = enriched.map(({ it, idx, curve }) => {
      let normalized: { x: string; y: number }[];
      if (mode === "anchor_to_longest" && anchorCurve) {
        const startDate = curve[0].x;
        const anchorValue = valueAtOrBefore(anchorCurve, startDate);
        normalized = normalizeCurve(curve, "anchor_to_longest", anchorValue);
      } else {
        normalized = normalizeCurve(curve, mode);
      }
      return {
        label: it.label,
        data: normalized.map((p) => ({ x: p.x, y: p.y })),
        borderColor: COLORS[idx % COLORS.length],
        backgroundColor: "transparent",
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.1,
      };
    }) as Array<Record<string, unknown>>;

    return { datasets };
  }, [items, mode]);

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
            label: (ctx: { dataset?: { label?: string }; parsed?: { y?: number } }) => {
              const y = ctx.parsed?.y;
              if (mode === "start_at_100") return `${ctx.dataset?.label ?? ""}: ${Number(y).toFixed(2)}`;
              return `${ctx.dataset?.label ?? ""}: $${Number(y).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
            },
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
            callback: (v: string | number) =>
              mode === "start_at_100"
                ? Number(v).toFixed(0)
                : `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
          },
          grid: { color: grid },
        },
      },
    };
  }, [theme, mode]);

  const tableRows = useMemo(
    () =>
      items.map((it) => {
        const m = it.results?.portfolio_results?.[0]?.metrics || {};
        return {
          id: it.id,
          label: it.label,
          status: it.run?.status || "?",
          cagr: pickNum(m, "cagr"),
          sharpe: pickNum(m, "sharpe_ratio", "sharpe"),
          sortino: pickNum(m, "sortino_ratio", "sortino"),
          maxDd: pickNum(m, "max_drawdown"),
          vol: pickNum(m, "volatility", "vol"),
          totalRet: pickNum(m, "total_return"),
          final: pickNum(m, "final_value"),
        };
      }),
    [items],
  );

  if (runIds.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-xl font-semibold">Compare runs</h1>
        <Card className="shadow-none">
          <CardContent className="py-8 text-sm text-muted-foreground">
            No runs selected. Open <Link className="underline" href="/runs">Runs</Link>, pick 2 or more,
            and click <span className="font-semibold">Compare selected</span>.
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold">Compare runs</h1>
          <p className="text-sm text-muted-foreground">
            {runIds.length} run{runIds.length === 1 ? "" : "s"} side-by-side. Share this URL to share the comparison.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as NormalizationMode)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            <option value="start_at_100">Start at $100 (shape)</option>
            <option value="anchor_to_longest">Anchor to longest curve</option>
            <option value="raw">Portfolio value (raw)</option>
          </select>
          <Link href="/runs">
            <Button variant="outline" size="sm">Back to Runs</Button>
          </Link>
        </div>
      </div>

      {loading ? <div className="text-sm text-muted-foreground">Loading…</div> : null}

      {!loading && chartData.datasets.length > 0 ? (
        <Card className="shadow-none">
          <CardContent className="p-4">
            <div className="mb-2 text-sm font-semibold">Equity curves</div>
            <div className="h-[380px]">
              <Line data={chartData as never} options={chartOptions as never} />
            </div>
          </CardContent>
        </Card>
      ) : !loading ? (
        <Card className="shadow-none">
          <CardContent className="py-6 text-sm text-muted-foreground">
            No equity curves available — runs may still be running or failed before producing artifacts.
          </CardContent>
        </Card>
      ) : null}

      {!loading && tableRows.length > 0 ? (
        <Card className="shadow-none">
          <CardContent className="p-0">
            <div className="border-b px-4 py-3 text-sm font-semibold">Metrics</div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th className="px-4 py-2 font-medium">Run</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                    <th className="px-4 py-2 font-medium">CAGR</th>
                    <th className="px-4 py-2 font-medium">Sharpe</th>
                    <th className="px-4 py-2 font-medium">Sortino</th>
                    <th className="px-4 py-2 font-medium">Max DD</th>
                    <th className="px-4 py-2 font-medium">Vol</th>
                    <th className="px-4 py-2 font-medium">Total ret.</th>
                    <th className="px-4 py-2 font-medium">Final value</th>
                  </tr>
                </thead>
                <tbody>
                  {tableRows.map((row, idx) => (
                    <tr key={row.id} className="border-b border-border/50">
                      <td className="px-4 py-2">
                        <span
                          className="mr-2 inline-block h-2 w-2 rounded-full"
                          style={{ backgroundColor: COLORS[idx % COLORS.length] }}
                        />
                        <Link
                          href={`/runs/${encodeURIComponent(row.id)}`}
                          className="font-medium hover:underline"
                        >
                          {row.label}
                        </Link>
                      </td>
                      <td className="px-4 py-2">
                        <Badge
                          variant={
                            row.status === "SUCCESS"
                              ? "success"
                              : row.status === "ERROR"
                              ? "danger"
                              : "secondary"
                          }
                        >
                          {row.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-2 font-mono text-xs">{fmtPct(row.cagr)}</td>
                      <td className="px-4 py-2 font-mono text-xs">{fmtNum(row.sharpe)}</td>
                      <td className="px-4 py-2 font-mono text-xs">{fmtNum(row.sortino)}</td>
                      <td className="px-4 py-2 font-mono text-xs">{fmtPct(row.maxDd)}</td>
                      <td className="px-4 py-2 font-mono text-xs">{fmtPct(row.vol)}</td>
                      <td className="px-4 py-2 font-mono text-xs">{fmtPct(row.totalRet)}</td>
                      <td className="px-4 py-2 font-mono text-xs">
                        {row.final != null ? `$${row.final.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {items.some((i) => i.error) ? (
        <Card className="shadow-none border-destructive/30">
          <CardContent className="py-3 text-xs text-destructive">
            Some runs could not be loaded:
            <ul className="mt-1 list-disc pl-5">
              {items
                .filter((i) => i.error)
                .map((i) => (
                  <li key={i.id}>
                    <code>{i.id}</code>: {i.error}
                  </li>
                ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
