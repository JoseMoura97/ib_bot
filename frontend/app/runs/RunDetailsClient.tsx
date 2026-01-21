"use client";

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
    <main style={{ maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: "8px 0 6px" }}>Run Details</h2>
          <div style={{ fontSize: 12, color: "#666" }}>
            Run ID: <code>{props.runId}</code>
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <a href="/dashboard" style={{ fontSize: 12 }}>
            ← Back to Dashboard
          </a>
        </div>
      </div>

      {errorMsg ? (
        <div style={{ marginTop: 12, background: "#fff3f3", border: "1px solid #f3b0b0", padding: 10, borderRadius: 8, color: "#b00020" }}>
          {errorMsg}
        </div>
      ) : null}

      {loading && !run ? <div style={{ marginTop: 12 }}>Loading…</div> : null}

      {run ? (
        <div style={{ marginTop: 12, border: "1px solid #eee", borderRadius: 12, padding: 12, background: "white" }}>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center" }}>
            <div>
              <div style={{ fontSize: 11, color: "#666", textTransform: "uppercase" }}>Status</div>
              <div style={{ fontSize: 18, fontWeight: 800 }}>{run.status}</div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: "#666", textTransform: "uppercase" }}>Type</div>
              <div style={{ fontSize: 14, fontWeight: 700 }}>{run.type}</div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: "#666", textTransform: "uppercase" }}>Stage</div>
              <div style={{ fontSize: 14, fontWeight: 700 }}>{run.progress?.stage || "—"}</div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: "#666", textTransform: "uppercase" }}>Created</div>
              <div style={{ fontSize: 12 }}>{fmtTs(run.created_at)}</div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: "#666", textTransform: "uppercase" }}>Started</div>
              <div style={{ fontSize: 12 }}>{fmtTs(run.started_at)}</div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: "#666", textTransform: "uppercase" }}>Finished</div>
              <div style={{ fontSize: 12 }}>{fmtTs(run.finished_at)}</div>
            </div>
          </div>

          {run.error ? (
            <div style={{ marginTop: 10, background: "#fff3f3", border: "1px solid #f3b0b0", padding: 10, borderRadius: 8, color: "#b00020" }}>
              <strong>Error:</strong> {run.error}
            </div>
          ) : null}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
            <div style={{ border: "1px solid #eee", borderRadius: 10, padding: 10, background: "#fafafa" }}>
              <div style={{ fontWeight: 700, marginBottom: 8 }}>Run params</div>
              <div style={{ fontSize: 12, color: "#444", display: "grid", gap: 6 }}>
                <div>
                  <strong>Mode:</strong> {String(run.params?.mode || "—")}
                </div>
                <div>
                  <strong>Start:</strong> {String(run.params?.start_date || "—")} <strong style={{ marginLeft: 8 }}>End:</strong>{" "}
                  {String(run.params?.end_date || "—")}
                </div>
                <div>
                  <strong>Cost bps:</strong> {String(run.params?.transaction_cost_bps ?? "0")}
                </div>
                <div>
                  <strong>Portfolio:</strong> {String(run.params?.portfolio_id || "—")}
                </div>
              </div>
            </div>
            <div style={{ border: "1px solid #eee", borderRadius: 10, padding: 10, background: "#fafafa" }}>
              <div style={{ fontWeight: 700, marginBottom: 8 }}>Strategies ({strategyParams.length})</div>
              {strategyParams.length ? (
                <div style={{ display: "grid", gap: 6, maxHeight: 180, overflow: "auto", paddingRight: 6 }}>
                  {strategyParams.map((s) => (
                    <div key={s.name} style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.name}</div>
                      <div style={{ fontSize: 12, color: "#666" }}>{(s.weight * 100).toFixed(1)}%</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: 12, color: "#666" }}>No strategies captured in run params.</div>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {run && run.status === "RUNNING" ? <div style={{ marginTop: 12, color: "#666" }}>Polling status…</div> : null}

      {run && run.status === "SUCCESS" && results ? (
        <div style={{ marginTop: 12 }}>
          <h3 style={{ margin: "10px 0" }}>Results</h3>

          {portfolioResult ? (
            <>
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                {Object.entries(portfolioResult.metrics || {}).map(([k, v]) => (
                  <div key={k} style={{ padding: "10px 12px", border: "1px solid #eee", borderRadius: 10, background: "white" }}>
                    <div style={{ fontSize: 11, color: "#666", textTransform: "uppercase" }}>{k}</div>
                    <div style={{ fontSize: 16, fontWeight: 800 }}>
                      {typeof v === "number" ? (Number.isFinite(v) ? v.toFixed(4) : String(v)) : String(v)}
                    </div>
                  </div>
                ))}
              </div>

              <div style={{ marginTop: 12, border: "1px solid #eee", borderRadius: 12, padding: 12, height: 520, background: "white" }}>
                {equityCurve?.length ? <Line data={chartData as any} options={chartOptions as any} /> : <div style={{ color: "#666" }}>No equity curve artifact.</div>}
              </div>
            </>
          ) : (
            <div style={{ color: "#666" }}>No portfolio results found for this run.</div>
          )}
        </div>
      ) : null}

      {run && run.status === "SUCCESS" && !results ? <div style={{ marginTop: 12, color: "#666" }}>Loading results…</div> : null}
    </main>
  );
}

