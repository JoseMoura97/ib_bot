"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "../_components/ui/Button";

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

export function RunsListClient(props: { runs: Run[] }) {
  const router = useRouter();
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Only successful portfolio_backtest runs are meaningful to compare; everything
  // else either has no equity curve or is the wrong shape. Disable checkboxes
  // for ineligible rows but still show them in the list.
  const isCompareable = (r: Run) =>
    r.type === "portfolio_backtest" && r.status === "SUCCESS";

  const compareUrl = useMemo(() => {
    const ids = Array.from(selected).filter(Boolean);
    return ids.length >= 2 ? `/portfolios/compare?runs=${ids.join(",")}` : null;
  }, [selected]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function compareNow() {
    if (!compareUrl) return;
    router.push(compareUrl);
  }

  const eligibleCount = props.runs.filter(isCompareable).length;

  return (
    <div className="rounded-xl border bg-card shadow-none">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3">
        <div className="text-sm font-semibold">Latest runs ({props.runs?.length ?? 0})</div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span>
            {selected.size} selected
            {selected.size === 1 ? " (need ≥2 to compare)" : ""}
          </span>
          <Button
            size="sm"
            onClick={compareNow}
            disabled={selected.size < 2}
            variant={selected.size >= 2 ? "primary" : "outline"}
          >
            Compare selected
          </Button>
        </div>
      </div>
      <div className="divide-y">
        {(props.runs || []).map((r) => {
          const eligible = isCompareable(r);
          const checked = selected.has(r.id);
          return (
            <div
              key={r.id}
              className="flex items-start gap-3 px-5 py-3 text-sm hover:bg-muted/40"
            >
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 cursor-pointer rounded border-input"
                checked={checked}
                onChange={() => toggle(r.id)}
                disabled={!eligible}
                title={eligible ? "Select for comparison" : "Only successful portfolio_backtest runs are compareable"}
              />
              <Link
                href={`/runs/${encodeURIComponent(r.id)}`}
                className="block flex-1"
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
            </div>
          );
        })}
        {!props.runs?.length ? <div className="px-5 py-6 text-sm text-muted-foreground">No runs yet.</div> : null}
      </div>
      {eligibleCount === 0 && (props.runs?.length ?? 0) > 0 ? (
        <div className="border-t px-5 py-3 text-xs text-muted-foreground">
          No successful portfolio_backtest runs to compare yet.
        </div>
      ) : null}
    </div>
  );
}
