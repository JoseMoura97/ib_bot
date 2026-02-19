"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "../_components/ui/Button";
import { Card, CardContent } from "../_components/ui/Card";
import { Input } from "../_components/ui/Input";
import { Select } from "../_components/ui/Select";
import { Table, TableWrap, Td, Th } from "../_components/ui/Table";

type MetricsRow = {
  name: string;
  category?: string;
  subcategory?: string;
  benchmark?: string;
  quiver: Record<string, any>;
  ours: Record<string, any>;
  diffs: Record<string, number | null>;
};

type MetricsPayload = {
  benchmark: string;
  generated_at?: string;
  rows: MetricsRow[];
};

type SortKey =
  | "name"
  | "mismatch_score"
  | "cagr_diff"
  | "sharpe_diff"
  | "maxdd_diff"
  | "beta_diff"
  | "alpha_diff"
  | "info_ratio_diff";

function num(v: any): number | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  const s = String(v).trim();
  if (!s) return null;
  if (s.endsWith("%")) {
    const x = Number(s.slice(0, -1));
    return Number.isFinite(x) ? x : null;
  }
  const x = Number(s);
  return Number.isFinite(x) ? x : null;
}

function fmtPct(v: any): string {
  const x = num(v);
  if (x === null) return "—";
  return `${x.toFixed(2)}%`;
}
function fmtNum(v: any, digits = 2): string {
  const x = num(v);
  if (x === null) return "—";
  return x.toFixed(digits);
}
function clsDiff(v: number | null): string {
  if (v === null) return "";
  if (v > 0) return "text-emerald-600 dark:text-emerald-400";
  if (v < 0) return "text-destructive";
  return "text-muted-foreground";
}

export function MetricsTable() {
  const [payload, setPayload] = useState<MetricsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("cagr_diff");
  const [sortDesc, setSortDesc] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMsg, setRefreshMsg] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/metrics/strategies", { cache: "no-store" });
      if (!res.ok) throw new Error(`API error ${res.status}`);
      const data = (await res.json()) as MetricsPayload;
      setPayload(data);
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const rows = useMemo(() => {
    const all = payload?.rows || [];
    const q = filter.trim().toLowerCase();
    const filtered = q
      ? all.filter((r) => {
          const hay = `${r.name} ${(r.category ?? "")} ${(r.subcategory ?? "")}`.toLowerCase();
          return hay.includes(q);
        })
      : all;

    function keyVal(r: MetricsRow): number {
      const d = r.diffs || {};
      const v =
        sortKey === "name"
          ? null
          : sortKey === "mismatch_score"
            ? (() => {
                const a = typeof d.cagr === "number" ? Math.abs(d.cagr) : 0;
                const b = typeof d.sharpe === "number" ? Math.abs(d.sharpe) : 0;
                const c = typeof d.max_drawdown === "number" ? Math.abs(d.max_drawdown) : 0;
                // Unweighted sum is simple + easy to reason about.
                return a + b + c;
              })()
          : sortKey === "cagr_diff"
            ? d.cagr
            : sortKey === "sharpe_diff"
              ? d.sharpe
              : sortKey === "maxdd_diff"
                ? d.max_drawdown
                : sortKey === "beta_diff"
                  ? d.beta
                  : sortKey === "alpha_diff"
                    ? d.alpha
                    : sortKey === "info_ratio_diff"
                      ? d.info_ratio
                      : null;
      return typeof v === "number" ? v : -Infinity;
    }

    const sorted = filtered.slice().sort((a, b) => {
      if (sortKey === "name") return a.name.localeCompare(b.name);
      const av = keyVal(a);
      const bv = keyVal(b);
      return (bv - av) * (sortDesc ? 1 : -1);
    });
    return sorted;
  }, [payload, filter, sortKey, sortDesc]);

  const showCategory = useMemo(() => rows.some((r) => !!r.category), [rows]);
  const showSubcategory = useMemo(() => rows.some((r) => !!r.subcategory), [rows]);

  const topMismatches = useMemo(() => {
    const all = payload?.rows || [];
    const scored = all
      .map((r) => {
        const d = r.diffs || {};
        const score =
          (typeof d.cagr === "number" ? Math.abs(d.cagr) : 0) +
          (typeof d.sharpe === "number" ? Math.abs(d.sharpe) : 0) +
          (typeof d.max_drawdown === "number" ? Math.abs(d.max_drawdown) : 0);
        return { r, score };
      })
      .filter((x) => x.score > 0);
    scored.sort((a, b) => b.score - a.score);
    return scored.slice(0, 10);
  }, [payload]);

  if (loading) return <div className="text-sm text-muted-foreground">Loading metrics…</div>;
  if (error) return <div className="text-sm text-destructive">Metrics error: {error}</div>;
  if (!payload) return <div className="text-sm text-muted-foreground">No metrics</div>;

  async function refreshValidation() {
    setRefreshing(true);
    setRefreshMsg(null);
    try {
      const res = await fetch("/api/metrics/strategies/refresh?force=true&max_age_hours=0", { method: "POST" });
      if (!res.ok) throw new Error(`API error ${res.status}`);
      setRefreshMsg("Queued validation refresh. It may take a while; use Reload to pull updated metrics when finished.");
    } catch (e: any) {
      setRefreshMsg(String(e?.message || e));
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold tracking-tight">Metrics comparison</h2>
          <p className="text-sm text-muted-foreground">
            Benchmark: <span className="font-semibold text-foreground">{payload.benchmark}</span>
            {payload.generated_at ? <> · Generated: {new Date(payload.generated_at).toLocaleString()}</> : null}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="w-56">
            <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter name/category…" />
          </div>
          <Select value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)} className="w-auto">
            <option value="mismatch_score">Sort by Mismatch score</option>
            <option value="cagr_diff">Sort by ΔCAGR</option>
            <option value="sharpe_diff">Sort by ΔSharpe</option>
            <option value="maxdd_diff">Sort by ΔMaxDD</option>
            <option value="beta_diff">Sort by ΔBeta</option>
            <option value="alpha_diff">Sort by ΔAlpha</option>
            <option value="info_ratio_diff">Sort by ΔInfoRatio</option>
            <option value="name">Sort by Name</option>
          </Select>
          <Button onClick={() => setSortDesc((v) => !v)} size="sm" variant="outline">
            {sortDesc ? "Desc" : "Asc"}
          </Button>
          <Button onClick={() => load()} size="sm" variant="outline">
            Reload
          </Button>
          <Button onClick={() => refreshValidation()} disabled={refreshing} size="sm" variant="secondary">
            {refreshing ? "Queuing…" : "Refresh validation"}
          </Button>
        </div>
      </div>

      {refreshMsg ? (
        <Card className="shadow-none">
          <CardContent className="py-4 text-sm text-muted-foreground">{refreshMsg}</CardContent>
        </Card>
      ) : null}

      {topMismatches.length ? (
        <Card className="shadow-none">
          <CardContent className="py-4">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm font-semibold">Top mismatches</div>
                <div className="text-xs text-muted-foreground">
                  Ranked by |ΔCAGR| + |ΔSharpe| + |ΔMaxDD| (top 10).
                </div>
              </div>
            </div>
            <div className="mt-3 overflow-x-auto">
              <Table className="min-w-[680px]">
                <thead>
                  <tr>
                    <Th>Strategy</Th>
                    <Th className="text-right">ΔCAGR</Th>
                    <Th className="text-right">ΔSharpe</Th>
                    <Th className="text-right">ΔMaxDD</Th>
                  </tr>
                </thead>
                <tbody>
                  {topMismatches.map(({ r }) => {
                    const d = r.diffs || {};
                    return (
                      <tr key={r.name} className="hover:bg-accent/40">
                        <Td className="max-w-[360px] truncate font-semibold">{r.name}</Td>
                        <Td className={`text-right font-mono ${clsDiff(d.cagr ?? null)}`}>
                          {typeof d.cagr === "number" ? `${d.cagr.toFixed(2)}%` : "—"}
                        </Td>
                        <Td className={`text-right font-mono ${clsDiff(d.sharpe ?? null)}`}>
                          {typeof d.sharpe === "number" ? d.sharpe.toFixed(2) : "—"}
                        </Td>
                        <Td className={`text-right font-mono ${clsDiff(d.max_drawdown ?? null)}`}>
                          {typeof d.max_drawdown === "number" ? `${d.max_drawdown.toFixed(2)}%` : "—"}
                        </Td>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <TableWrap>
        <Table>
          <thead>
            <tr>
              <Th>Strategy</Th>
              <Th>Status</Th>
              {showCategory ? <Th>Category</Th> : null}
              {showSubcategory ? <Th>Subcategory</Th> : null}

              <Th className="text-right">CAGR (Our)</Th>
              <Th className="text-right">CAGR (Q)</Th>
              <Th className="text-right">ΔCAGR</Th>

              <Th className="text-right">Sharpe (Our)</Th>
              <Th className="text-right">Sharpe (Q)</Th>
              <Th className="text-right">ΔSharpe</Th>

              <Th className="text-right">MaxDD (Our)</Th>
              <Th className="text-right">MaxDD (Q)</Th>
              <Th className="text-right">ΔMaxDD</Th>

              <Th className="text-right">Beta (Our)</Th>
              <Th className="text-right">Beta (Q)</Th>
              <Th className="text-right">ΔBeta</Th>

              <Th className="text-right">Alpha (Our)</Th>
              <Th className="text-right">Alpha (Q)</Th>
              <Th className="text-right">ΔAlpha</Th>

              <Th className="text-right">IR (Our)</Th>
              <Th className="text-right">IR (Q)</Th>
              <Th className="text-right">ΔIR</Th>

              <Th className="text-right">Treynor (Our)</Th>
              <Th className="text-right">Treynor (Q)</Th>
              <Th className="text-right">ΔTreynor</Th>

              <Th className="text-right">Win% (Our)</Th>
              <Th className="text-right">Win% (Q)</Th>
              <Th className="text-right">ΔWin%</Th>

              <Th className="text-right">Trades (Our)</Th>
              <Th className="text-right">Trades (Q)</Th>
              <Th className="text-right">ΔTrades</Th>

              <Th className="text-right">Vol (Our)</Th>
              <Th className="text-right">Vol (Q)</Th>
              <Th className="text-right">ΔVol</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const d = r.diffs || {};
              const status = String(r.ours?.status ?? "—");
              return (
                <tr key={r.name} className="hover:bg-accent/40">
                  <Td className="max-w-[260px] truncate font-semibold">{r.name}</Td>
                  <Td className={status === "OK" ? "text-muted-foreground" : "text-muted-foreground"}>
                    {status}
                  </Td>
                  {showCategory ? <Td className="text-muted-foreground">{r.category ?? ""}</Td> : null}
                  {showSubcategory ? <Td className="text-muted-foreground">{r.subcategory ?? ""}</Td> : null}

                  <Td className="text-right font-mono">{fmtPct(r.ours?.cagr)}</Td>
                  <Td className="text-right font-mono">{fmtPct(r.quiver?.cagr)}</Td>
                  <Td className={`text-right font-mono ${clsDiff(d.cagr ?? null)}`}>
                    {d.cagr === null || d.cagr === undefined ? "—" : `${d.cagr.toFixed(2)}%`}
                  </Td>

                  <Td className="text-right font-mono">{fmtNum(r.ours?.sharpe)}</Td>
                  <Td className="text-right font-mono">{fmtNum(r.quiver?.sharpe)}</Td>
                  <Td className={`text-right font-mono ${clsDiff(d.sharpe ?? null)}`}>
                    {d.sharpe === null || d.sharpe === undefined ? "—" : d.sharpe.toFixed(2)}
                  </Td>

                  <Td className="text-right font-mono">{fmtPct(r.ours?.max_drawdown)}</Td>
                  <Td className="text-right font-mono">{fmtPct(r.quiver?.max_drawdown)}</Td>
                  <Td className={`text-right font-mono ${clsDiff(d.max_drawdown ?? null)}`}>
                    {d.max_drawdown === null || d.max_drawdown === undefined ? "—" : `${d.max_drawdown.toFixed(2)}%`}
                  </Td>

                  <Td className="text-right font-mono">{fmtNum(r.ours?.beta)}</Td>
                  <Td className="text-right font-mono">{fmtNum(r.quiver?.beta)}</Td>
                  <Td className={`text-right font-mono ${clsDiff(d.beta ?? null)}`}>
                    {d.beta === null || d.beta === undefined ? "—" : d.beta.toFixed(2)}
                  </Td>

                  <Td className="text-right font-mono">{fmtNum(r.ours?.alpha)}</Td>
                  <Td className="text-right font-mono">{fmtNum(r.quiver?.alpha)}</Td>
                  <Td className={`text-right font-mono ${clsDiff(d.alpha ?? null)}`}>
                    {d.alpha === null || d.alpha === undefined ? "—" : d.alpha.toFixed(2)}
                  </Td>

                  <Td className="text-right font-mono">{fmtNum(r.ours?.info_ratio)}</Td>
                  <Td className="text-right font-mono">{fmtNum(r.quiver?.info_ratio)}</Td>
                  <Td className={`text-right font-mono ${clsDiff(d.info_ratio ?? null)}`}>
                    {d.info_ratio === null || d.info_ratio === undefined ? "—" : d.info_ratio.toFixed(2)}
                  </Td>

                  <Td className="text-right font-mono">{fmtNum(r.ours?.treynor)}</Td>
                  <Td className="text-right font-mono">{fmtNum(r.quiver?.treynor)}</Td>
                  <Td className={`text-right font-mono ${clsDiff(d.treynor ?? null)}`}>
                    {d.treynor === null || d.treynor === undefined ? "—" : d.treynor.toFixed(2)}
                  </Td>

                  <Td className="text-right font-mono">{fmtPct(r.ours?.win_rate)}</Td>
                  <Td className="text-right font-mono">{fmtPct(r.quiver?.win_rate)}</Td>
                  <Td className={`text-right font-mono ${clsDiff(d.win_rate ?? null)}`}>
                    {d.win_rate === null || d.win_rate === undefined ? "—" : `${d.win_rate.toFixed(2)}%`}
                  </Td>

                  <Td className="text-right font-mono">{fmtNum(r.ours?.trades, 0)}</Td>
                  <Td className="text-right font-mono">{fmtNum(r.quiver?.trades, 0)}</Td>
                  <Td className={`text-right font-mono ${clsDiff(d.trades ?? null)}`}>
                    {d.trades === null || d.trades === undefined ? "—" : d.trades.toFixed(0)}
                  </Td>

                  <Td className="text-right font-mono">{fmtPct(r.ours?.volatility)}</Td>
                  <Td className="text-right font-mono">{fmtPct(r.quiver?.volatility)}</Td>
                  <Td className={`text-right font-mono ${clsDiff(d.volatility ?? null)}`}>
                    {d.volatility === null || d.volatility === undefined ? "—" : `${d.volatility.toFixed(2)}%`}
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      </TableWrap>
    </section>
  );
}

