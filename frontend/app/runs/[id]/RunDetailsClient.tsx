"use client";

import { useEffect, useMemo, useState } from "react";

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

export function RunDetailsClient(props: { runId: string }) {
  const runId = props.runId;
  const [run, setRun] = useState<Run | null>(null);
  const [results, setResults] = useState<any>(null);
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

      // Best-effort results fetch (may 404 before worker finishes).
      const rr = await fetch(`/api/runs/${encodeURIComponent(runId)}/results`, { cache: "no-store" });
      if (rr.ok) {
        setResults(await rr.json());
      }
    } catch (e: any) {
      setError(String(e?.message || e));
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

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1>Run</h1>
        <p className="text-sm text-muted-foreground">
          ID: <code className="rounded bg-muted px-1.5 py-0.5">{runId}</code>
        </p>
      </div>

      {loading ? <div className="text-sm text-muted-foreground">Loading…</div> : null}
      {error ? <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">{error}</div> : null}

      {run ? (
        <div className="rounded-xl border bg-card p-5 text-sm shadow-none">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-xs text-muted-foreground">Type</div>
              <div className="text-base font-semibold">{run.type}</div>
            </div>
            <div className="text-right">
              <div className="text-xs text-muted-foreground">Status</div>
              <div className="text-base font-semibold">{run.status}</div>
            </div>
          </div>
          <div className="mt-3 grid gap-2 text-xs text-muted-foreground">
            <div>Created: {fmtTime(run.created_at)}</div>
            <div>Started: {fmtTime(run.started_at)}</div>
            <div>Finished: {fmtTime(run.finished_at)}</div>
          </div>
          {run.error ? <div className="mt-3 text-sm text-destructive">Error: {run.error}</div> : null}
        </div>
      ) : null}

      <div className="rounded-xl border bg-card shadow-none">
        <div className="border-b px-5 py-3 text-sm font-semibold">Params</div>
        <pre className="overflow-auto px-5 py-4 text-xs">{JSON.stringify(run?.params ?? {}, null, 2)}</pre>
      </div>

      <div className="rounded-xl border bg-card shadow-none">
        <div className="border-b px-5 py-3 text-sm font-semibold">Progress</div>
        <pre className="overflow-auto px-5 py-4 text-xs">{JSON.stringify(run?.progress ?? {}, null, 2)}</pre>
      </div>

      <div className="rounded-xl border bg-card shadow-none">
        <div className="border-b px-5 py-3 text-sm font-semibold">Results</div>
        <pre className="overflow-auto px-5 py-4 text-xs">{JSON.stringify(results ?? { hint: "Results appear after worker finishes." }, null, 2)}</pre>
      </div>
    </div>
  );
}

