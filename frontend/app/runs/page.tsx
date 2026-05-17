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
          Click any row to view the full result (equity curve, metrics, SPY overlay, per-strategy
          breakdown).{" "}
          <span className="font-medium text-foreground">
            To compare portfolios side-by-side: tick 2+ successful portfolio_backtest rows and click
            “Compare selected” at the top of the list.
          </span>
        </p>
      </div>

      <div className="rounded-xl border bg-card p-5 text-sm text-muted-foreground shadow-none">
        Tip: create new runs from{" "}
        <Link className="underline" href="/backtest">
          Backtest
        </Link>{" "}
        or{" "}
        <Link className="underline" href="/portfolios">
          Portfolios
        </Link>
        .
      </div>

      <RunsListClient runs={runs || []} />
    </div>
  );
}
