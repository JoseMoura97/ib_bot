"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "../../_components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "../../_components/ui/Card";
import { CodeBlock } from "../../_components/ui/CodeBlock";

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`API error ${res.status}${txt ? `: ${txt}` : ""}`);
  }
  return (await res.json()) as T;
}

export function RunDetailsClient(props: { runId: string }) {
  const [run, setRun] = useState<unknown>(null);
  const [results, setResults] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [r, rr] = await Promise.all([
        fetchJson(`/api/runs/${encodeURIComponent(props.runId)}`),
        fetchJson(`/api/runs/${encodeURIComponent(props.runId)}/results`).catch(() => null),
      ]);
      setRun(r);
      setResults(rr);
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.runId]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="truncate">Run</h1>
          <div className="text-xs text-muted-foreground">
            <Link href="/runs" className="font-medium text-foreground">
              Runs
            </Link>{" "}
            <span className="text-muted-foreground/70">/</span> <span className="font-mono">{props.runId}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => load()} disabled={loading}>
            {loading ? "Loading…" : "Refresh"}
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Run details</CardTitle>
          </CardHeader>
          <CardContent>{run ? <CodeBlock value={run} /> : <div className="text-sm text-muted-foreground">No data.</div>}</CardContent>
        </Card>

        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Results</CardTitle>
          </CardHeader>
          <CardContent>
            {results ? <CodeBlock value={results} /> : <div className="text-sm text-muted-foreground">No results yet.</div>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

