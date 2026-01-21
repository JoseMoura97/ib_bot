import Link from "next/link";

import { apiGet } from "../_lib/api";
import { PageHeader } from "../_components/PageHeader";
import { Card, CardContent } from "../_components/ui/Card";

type Run = {
  id: string;
  type: string;
  status: string;
  created_at?: string;
  error?: string | null;
};

function fmtTime(s: string | undefined | null): string {
  if (!s) return "—";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? String(s) : d.toLocaleString();
}

export default async function RunsPage() {
  let runs: Run[] = [];
  let err: string | null = null;
  try {
    runs = (await apiGet("/runs?limit=50")) as any;
  } catch (e: any) {
    err = String(e?.message || e);
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Runs" description="Runs are created from the dashboard backtest wizard." />

      <Card className="shadow-none">
        <CardContent className="space-y-3">
          {err ? <div className="text-sm text-destructive">Error: {err}</div> : null}
          <div className="text-sm font-medium">Latest runs ({runs.length})</div>
          <div className="divide-y rounded-lg border">
            {runs.map((r) => (
              <Link key={r.id} href={`/runs/${encodeURIComponent(r.id)}`} className="block px-4 py-3 text-sm hover:bg-muted/40">
                <div className="flex items-center justify-between gap-3">
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
            {!runs.length ? <div className="px-4 py-6 text-sm text-muted-foreground">No runs yet.</div> : null}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

