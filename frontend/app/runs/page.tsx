import Link from "next/link";

import { apiGet } from "../_lib/api";

type Run = {
  id: string;
  type: string;
  status: string;
  created_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
};

function fmtTime(s: string | undefined | null): string {
  if (!s) return "—";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? String(s) : d.toLocaleString();
}

export default async function RunsPage() {
  const runs = ((await apiGet("/runs?limit=50")) as any) as Run[];

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1>Runs</h1>
        <p className="text-sm text-muted-foreground">
          Runs are created from the dashboard backtest wizard. Click a run to view status and results.
        </p>
      </div>

      <div className="rounded-xl border bg-card p-5 text-sm text-muted-foreground shadow-none">
        Tip: If you don’t see runs yet, create one from <Link href="/dashboard">Dashboard</Link>.
      </div>

      <div className="rounded-xl border bg-card shadow-none">
        <div className="border-b px-5 py-3 text-sm font-semibold">Latest runs ({runs?.length ?? 0})</div>
        <div className="divide-y">
          {(runs || []).map((r) => (
            <Link
              key={r.id}
              href={`/runs/${encodeURIComponent(r.id)}`}
              className="block px-5 py-3 text-sm hover:bg-muted/40"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="font-semibold">{r.type}</div>
                  <div className="text-xs text-muted-foreground">{r.id}</div>
                </div>
                <div className="text-right">
                  <div className="font-semibold">{r.status}</div>
                  <div className="text-xs text-muted-foreground">Created {fmtTime(r.created_at)}</div>
                </div>
              </div>
              {r.error ? <div className="mt-2 text-xs text-destructive">Error: {r.error}</div> : null}
            </Link>
          ))}
          {!runs?.length ? <div className="px-5 py-6 text-sm text-muted-foreground">No runs yet.</div> : null}
        </div>
      </div>
    </div>
  );
}
