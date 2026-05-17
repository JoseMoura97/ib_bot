"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { RunResultsPanel } from "../../backtest/RunResultsPanel";
import { Button } from "../../_components/ui/Button";
import { Card, CardContent } from "../../_components/ui/Card";
import { Badge } from "../../_components/ui/Badge";

type Run = {
  id: string;
  type: string;
  status: string;
  params?: Record<string, unknown>;
  progress?: Record<string, unknown>;
  created_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
};

async function readErr(res: Response): Promise<string> {
  try {
    const txt = await res.text();
    return txt || `HTTP ${res.status}`;
  } catch {
    return `HTTP ${res.status}`;
  }
}

function fmtTime(s: string | undefined | null): string {
  if (!s) return "—";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? String(s) : d.toLocaleString();
}

function statusVariant(st: string): "success" | "secondary" | "danger" | "outline" {
  const u = st.toUpperCase();
  if (u === "SUCCESS") return "success";
  if (u === "ERROR") return "danger";
  if (u === "RUNNING" || u === "PENDING") return "secondary";
  return "outline";
}

export function RunDetailsClient(props: { runId: string }) {
  const runId = props.runId;
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const shouldPoll = useMemo(() => {
    const st = (run?.status || "").toUpperCase();
    return st === "PENDING" || st === "RUNNING";
  }, [run?.status]);

  async function loadOnce() {
    setError(null);
    try {
      const r = await fetch(`/api/runs/${encodeURIComponent(runId)}`, { cache: "no-store" });
      if (!r.ok) throw new Error(await readErr(r));
      const payload = (await r.json()) as Run;
      setRun(payload);
    } catch (e: unknown) {
      setError(String((e as Error)?.message || e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadOnce();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  useEffect(() => {
    if (!shouldPoll) return;
    const t = window.setInterval(() => {
      loadOnce();
    }, 1500);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldPoll, runId]);

  const isPortfolioBacktest = (run?.type || "").toLowerCase() === "portfolio_backtest";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold">
            {(run?.params as { portfolio_name?: string } | undefined)?.portfolio_name || "Run"}
          </h1>
          <p className="text-sm text-muted-foreground">
            {run?.type ? <span className="mr-2 rounded bg-muted px-1.5 py-0.5">{run.type}</span> : null}
            ID: <code className="rounded bg-muted px-1.5 py-0.5">{runId.slice(0, 8)}…</code>
          </p>
        </div>
        <Link href="/backtest">
          <Button variant="outline" size="sm">
            Back to Backtest
          </Button>
        </Link>
      </div>

      {loading ? <div className="text-sm text-muted-foreground">Loading…</div> : null}
      {error ? <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">{error}</div> : null}

      {run ? (
        <Card className="shadow-none">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
            <div>
              <div className="text-xs text-muted-foreground">Type</div>
              <div className="text-base font-semibold">{run.type}</div>
            </div>
            <div className="text-right">
              <div className="text-xs text-muted-foreground">Status</div>
              <Badge variant={statusVariant(run.status)} className="mt-1">
                {run.status}
              </Badge>
            </div>
          </CardContent>
          <div className="grid gap-2 border-t px-5 py-3 text-xs text-muted-foreground sm:grid-cols-3">
            <div>Created: {fmtTime(run.created_at)}</div>
            <div>Started: {fmtTime(run.started_at)}</div>
            <div>Finished: {fmtTime(run.finished_at)}</div>
          </div>
          {run.error ? <div className="border-t px-5 py-3 text-sm text-destructive">Error: {run.error}</div> : null}
        </Card>
      ) : null}

      {isPortfolioBacktest && run ? (
        <div className="space-y-3">
          <h2 className="text-base font-semibold">Results</h2>
          <RunResultsPanel runId={runId} runStatus={run.status} />
        </div>
      ) : null}

      <details className="rounded-xl border bg-card shadow-none">
        <summary className="cursor-pointer px-5 py-3 text-sm font-semibold">Technical: params &amp; progress</summary>
        <div className="grid gap-4 border-t p-5 md:grid-cols-2">
          <div>
            <div className="mb-2 text-xs font-medium text-muted-foreground">Params</div>
            <pre className="max-h-[320px] overflow-auto rounded-md bg-muted/30 p-3 text-xs">{JSON.stringify(run?.params ?? {}, null, 2)}</pre>
          </div>
          <div>
            <div className="mb-2 text-xs font-medium text-muted-foreground">Progress</div>
            <pre className="max-h-[320px] overflow-auto rounded-md bg-muted/30 p-3 text-xs">{JSON.stringify(run?.progress ?? {}, null, 2)}</pre>
          </div>
        </div>
      </details>

      {!isPortfolioBacktest && run ? (
        <Card className="shadow-none">
          <CardContent className="py-6 text-sm text-muted-foreground">
            Visual results panel is optimized for <code className="rounded bg-muted px-1">portfolio_backtest</code> runs. For this run
            type, use the technical section above or the API.
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
