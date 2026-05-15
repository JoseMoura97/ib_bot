import Link from "next/link";

import { apiGet } from "../_lib/api";
import { RunsListClient } from "./RunsListClient";

type Run = {
  id: string;
  type: string;
  status: string;
  created_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
};

export default async function RunsPage() {
  const runs = ((await apiGet("/runs?limit=50")) as any) as Run[];

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1>Runs</h1>
        <p className="text-sm text-muted-foreground">
          Runs are created from the dashboard backtest wizard. Click a run to view status and results,
          or tick 2+ successful portfolio_backtest runs and click <span className="font-semibold">Compare selected</span>.
        </p>
      </div>

      <div className="rounded-xl border bg-card p-5 text-sm text-muted-foreground shadow-none">
        Tip: If you don’t see runs yet, create one from <Link href="/dashboard">Dashboard</Link>.
      </div>

      <RunsListClient runs={runs || []} />
    </div>
  );
}
