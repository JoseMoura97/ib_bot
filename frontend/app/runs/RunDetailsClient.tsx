"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
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
import { PageHeader } from "../_components/PageHeader";
import { Button } from "../_components/ui/Button";
import { Card, CardContent } from "../_components/ui/Card";
import { Table, TableWrap, Td, Th } from "../_components/ui/Table";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, TimeScale, Tooltip, Legend);

type RunOut = {
  id: string;
  type: string;
  status: "PENDING" | "RUNNING" | "SUCCESS" | "ERROR" | string;
  params: Record<string, any>;
  progress: Record<string, any>;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
};

type RunResults = {
  run: { id: string; type: string; status: string };
  portfolio_results: Array<{
    portfolio_id: string;
    mode: string;
    metrics: Record<string, any>;
    artifacts: Record<string, any>;
  }>;
  strategy_results: Array<{
    strategy_name: string;
    metrics: Record<string, any>;
    artifacts: Record<string, any>;
  }>;
};

async function readErrorBody(res: Response): Promise<string> {
  try {
    const txt = await res.text();
    return txt || `HTTP ${res.status}`;
  } catch {
    return `HTTP ${res.status}`;
  }
}

function fmtTs(ts?: string | null): string {
  if (!ts) return "—";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? String(ts) : d.toLocaleString();
}

function isTerminal(status: string): boolean {
  return status === "SUCCESS" || status === "ERROR";
}

export function RunDetailsClient(props: { runId: string }) {
  const [run, setRun] = useState<RunOut | null>(null);
  const [results, setResults] = useState<RunResults | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchedResultsRef = useRef(false);

  async function fetchRun() {
    const res = await fetch(`/api/runs/${encodeURIComponent(props.runId)}`, { cache: "no-store" });
    if (!res.ok) throw new Error(await readErrorBody(res));
    const data = (await res.json()) as RunOut;
    setRun(data);
    return data;
  }

  async function fetchResults() {
    const res = await fetch(`/api/runs/${encodeURIComponent(props.runId)}/results`, { cache: "no-store" });
    if (!res.ok) throw new Error(await readErrorBody(res));
    const data = (await res.json()) as RunResults;
    setResults(data);
    return data;
  }

  useEffect(() => {
    let mounted = true;
    let t: any = null;
    setLoading(true);
    setErrorMsg(null);

    const tick = async () => {
      try {
        const r = await fetchRun();
        if (!mounted) return;

        if (r.status === "SUCCESS" && !fetchedResultsRef.current) {
          fetchedResultsRef.current = true;
          await fetchResults();
        }
        if (r.status === "ERROR") {
          fetchedResultsRef.current = true;
        }
      } catch (e: any) {
        if (!mounted) return;
        setErrorMsg(String(e?.message || e));
      } finally {
        if (mounted) setLoading(false);
      }
    };

    // Kick immediately, then poll until terminal.
    tick();
    t = window.setInterval(async () => {
      try {
        const r = await fetchRun();
        if (!mounted) return;
        if (isTerminal(r.status)) {
          window.clearInterval(t);
          if (r.status === "SUCCESS" && !fetchedResultsRef.current) {
            fetchedResultsRef.current = true;
            await fetchResults();
          }
        }
      } catch (e: any) {
        if (!mounted) return;
        setErrorMsg(String(e?.message || e));
      }
    }, 2000);

    return () => {
      mounted = false;
      if (t) window.clearInterval(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.runId]);

  const portfolioResult = results?.portfolio_results?.[0] || null;
  const equityCurve = (portfolioResult?.artifacts?.equity_curve || []) as Array<{ date: string; value: number }>;

  const chartData = useMemo(() => {
    const pts = (equityCurve || []).map((p) => ({ x: p.date, y: p.value }));
    return {
      datasets: [
        {
          label: "Portfolio Equity",
          data: pts,
          borderColor: "#7aa2f7",
          backgroundColor: "transparent",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.1,
        },
      ],
    };
  }, [equityCurve]);

  const chartOptions = useMemo(() => {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index" as const, intersect: false },
      plugins: { legend: { position: "top" as const } },
      scales: {
        x: { type: "time" as const, time: { unit: "month" as const } },
        y: { title: { display: true, text: "Equity" } },
      },
    };
  }, []);

  const strategyParams = useMemo(() => {
    const raw = (run?.params?.strategies || []) as Array<{ name?: string; weight?: number }>;
    return raw
      .filter((s) => !!s?.name)
      .map((s) => ({ name: String(s.name), weight: Number(s.weight) || 0 }))
      .sort((a, b) => b.weight - a.weight);
  }, [run]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Run Details"
        description={`Run ID: ${props.runId}`}
        right={
          <Link href="/dashboard">
            <Button size="sm" variant="outline">
              Back to Dashboard
            </Button>
          </Link>
        }
      />

      {errorMsg ? (
        <Card className="border-destructive/30 bg-destructive/10 shadow-none">
          <CardContent className="py-4 text-sm text-destructive">{errorMsg}</CardContent>
        </Card>
      ) : null}

      {loading && !run ? <div className="text-sm text-muted-foreground">Loading…</div> : null}

      {run ? (
        <Card className="shadow-none">
          <CardContent className="space-y-4 py-4">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <div className="rounded-lg border bg-muted/30 px-3 py-2">
                <div className="text-xs font-semibold text-muted-foreground">Status</div>
                <div className="text-lg font-semibold">{run.status}</div>
              </div>
              <div className="rounded-lg border bg-muted/30 px-3 py-2">
                <div className="text-xs font-semibold text-muted-foreground">Type</div>
                <div className="text-sm font-semibold">{run.type}</div>
              </div>
              <div className="rounded-lg border bg-muted/30 px-3 py-2">
                <div className="text-xs font-semibold text-muted-foreground">Stage</div>
                <div className="text-sm font-semibold">{run.progress?.stage || "—"}</div>
              </div>
              <div className="rounded-lg border bg-muted/30 px-3 py-2">
                <div className="text-xs font-semibold text-muted-foreground">Created</div>
                <div className="text-xs">{fmtTs(run.created_at)}</div>
              </div>
              <div className="rounded-lg border bg-muted/30 px-3 py-2">
                <div className="text-xs font-semibold text-muted-foreground">Started</div>
                <div className="text-xs">{fmtTs(run.started_at)}</div>
              </div>
              <div className="rounded-lg border bg-muted/30 px-3 py-2">
                <div className="text-xs font-semibold text-muted-foreground">Finished</div>
                <div className="text-xs">{fmtTs(run.finished_at)}</div>
              </div>
            </div>

            {run.error ? (
              <Card className="border-destructive/30 bg-destructive/10 shadow-none">
                <CardContent className="py-4 text-sm text-destructive">
                  <span className="font-semibold">Error:</span> {run.error}
                </CardContent>
              </Card>
            ) : null}

            <div className="grid gap-4 lg:grid-cols-2">
              <Card className="shadow-none">
                <CardContent className="space-y-2 py-4">
                  <div className="text-sm font-semibold">Run params</div>
                  <div className="text-xs text-muted-foreground">Mode: {String(run.params?.mode || "—")}</div>
                  <div className="text-xs text-muted-foreground">
                    Start: {String(run.params?.start_date || "—")} · End: {String(run.params?.end_date || "—")}
                  </div>
                  <div className="text-xs text-muted-foreground">Cost bps: {String(run.params?.transaction_cost_bps ?? "0")}</div>
                  <div className="text-xs text-muted-foreground">Portfolio: {String(run.params?.portfolio_id || "—")}</div>
                </CardContent>
              </Card>

              <Card className="shadow-none">
                <CardContent className="space-y-3 py-4">
                  <div className="text-sm font-semibold">Strategies ({strategyParams.length})</div>
                  {strategyParams.length ? (
                    <TableWrap>
                      <Table>
                        <thead>
                          <tr>
                            <Th>Strategy</Th>
                            <Th className="text-right">Weight</Th>
                          </tr>
                        </thead>
                        <tbody>
                          {strategyParams.map((s) => (
                            <tr key={s.name} className="hover:bg-accent/40">
                              <Td className="max-w-[240px] truncate font-medium">{s.name}</Td>
                              <Td className="text-right font-mono">{(s.weight * 100).toFixed(1)}%</Td>
                            </tr>
                          ))}
                        </tbody>
                      </Table>
                    </TableWrap>
                  ) : (
                    <div className="text-xs text-muted-foreground">No strategies captured in run params.</div>
                  )}
                </CardContent>
              </Card>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {run && run.status === "RUNNING" ? <div className="text-sm text-muted-foreground">Polling status…</div> : null}

      {run && run.status === "SUCCESS" && results ? (
        <div className="space-y-4">
          <div className="text-lg font-semibold">Results</div>

          {portfolioResult ? (
            <>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {Object.entries(portfolioResult.metrics || {}).map(([k, v]) => (
                  <Card key={k} className="shadow-none">
                    <CardContent className="py-4">
                      <div className="text-xs font-semibold text-muted-foreground">{k}</div>
                      <div className="mt-1 text-lg font-semibold">
                        {typeof v === "number" ? (Number.isFinite(v) ? v.toFixed(4) : String(v)) : String(v)}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>

              <Card className="shadow-none">
                <CardContent className="h-[520px] p-4">
                  {equityCurve?.length ? (
                    <Line data={chartData as any} options={chartOptions as any} />
                  ) : (
                    <div className="text-sm text-muted-foreground">No equity curve artifact.</div>
                  )}
                </CardContent>
              </Card>
            </>
          ) : (
            <div className="text-sm text-muted-foreground">No portfolio results found for this run.</div>
          )}
        </div>
      ) : null}

      {run && run.status === "SUCCESS" && !results ? <div className="text-sm text-muted-foreground">Loading results…</div> : null}
    </div>
  );
}

