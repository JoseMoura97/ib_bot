"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

type StrategyOption = {
  name: string;
  category?: string;
  subcategory?: string;
  description?: string;
};

type WizardStrategy = {
  name: string;
  weight: number; // raw, will be normalized on submit
};

function todayIso(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function daysAgoIso(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

async function readErrorBody(res: Response): Promise<string> {
  try {
    const txt = await res.text();
    return txt || `HTTP ${res.status}`;
  } catch {
    return `HTTP ${res.status}`;
  }
}

function normalizeWeights(rows: WizardStrategy[]): WizardStrategy[] {
  const sum = rows.reduce((acc, r) => acc + (Number.isFinite(r.weight) ? r.weight : 0), 0);
  if (sum <= 0) return rows.map((r) => ({ ...r, weight: 0 }));
  return rows.map((r) => ({ ...r, weight: r.weight / sum }));
}

export function BacktestWizard(props: {
  strategies: StrategyOption[];
  defaultSelectedNames?: string[];
}) {
  const router = useRouter();

  const [filter, setFilter] = useState("");
  const [mode, setMode] = useState<"nav_blend" | "holdings_union">("nav_blend");
  const [startDate, setStartDate] = useState<string>(() => daysAgoIso(365 * 5));
  const [endDate, setEndDate] = useState<string>(() => todayIso());
  const [costBps, setCostBps] = useState<number>(0);
  const [initialCash, setInitialCash] = useState<number>(100000);

  const [selected, setSelected] = useState<WizardStrategy[]>(() => {
    const defaults = (props.defaultSelectedNames || []).slice(0, 10);
    if (!defaults.length) return [];
    const w = 1 / defaults.length;
    return defaults.map((name) => ({ name, weight: w }));
  });

  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const options = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const base = props.strategies || [];
    const filtered = q ? base.filter((s) => s.name.toLowerCase().includes(q)) : base;
    return filtered.slice().sort((a, b) => a.name.localeCompare(b.name));
  }, [props.strategies, filter]);

  const selectedSet = useMemo(() => new Set(selected.map((s) => s.name)), [selected]);

  function showToast(msg: string) {
    setToast(msg);
    window.setTimeout(() => setToast(null), 3000);
  }

  function toggleStrategy(name: string) {
    setSelected((prev) => {
      if (prev.some((r) => r.name === name)) return prev.filter((r) => r.name !== name);
      return [...prev, { name, weight: 1 }];
    });
  }

  function setWeight(name: string, weight: number) {
    setSelected((prev) => prev.map((r) => (r.name === name ? { ...r, weight } : r)));
  }

  function equalizeWeights() {
    setSelected((prev) => {
      const n = prev.length;
      if (!n) return prev;
      const w = 1 / n;
      return prev.map((r) => ({ ...r, weight: w }));
    });
  }

  async function onRun() {
    setErrorMsg(null);
    if (!selected.length) {
      setErrorMsg("Pick at least one strategy.");
      return;
    }
    if (!startDate || !endDate || endDate <= startDate) {
      setErrorMsg("Start/end dates are invalid (end_date must be after start_date).");
      return;
    }

    const normalized = normalizeWeights(selected);
    if (normalized.some((r) => !Number.isFinite(r.weight) || r.weight < 0)) {
      setErrorMsg("Weights must be non-negative numbers.");
      return;
    }

    setSubmitting(true);
    try {
      // 1) Create an ad-hoc portfolio to hold the strategy weights.
      const portfolioName = `Ad hoc backtest ${new Date().toISOString()}`;
      const pr = await fetch("/api/portfolios", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: portfolioName,
          description: "Created from dashboard backtest wizard",
          default_cash: Number(initialCash) || 0,
          settings: { source: "dashboard_backtest_wizard" },
        }),
      });
      if (!pr.ok) throw new Error(await readErrorBody(pr));
      const portfolio = (await pr.json()) as { id: string };

      // 2) Set portfolio strategies (enabled).
      const sr = await fetch(`/api/portfolios/${encodeURIComponent(portfolio.id)}/strategies`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          normalized.map((s) => ({
            strategy_name: s.name,
            enabled: true,
            weight: s.weight,
            overrides: {},
          })),
        ),
      });
      if (!sr.ok) throw new Error(await readErrorBody(sr));

      // 3) Create a portfolio-backtest run.
      const rr = await fetch("/api/runs/portfolio-backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          portfolio_id: portfolio.id,
          start_date: startDate,
          end_date: endDate,
          mode,
          transaction_cost_bps: Number(costBps) || 0,
        }),
      });
      if (!rr.ok) throw new Error(await readErrorBody(rr));
      const run = (await rr.json()) as { id: string };

      showToast("Run created — opening details…");
      router.push(`/runs/${encodeURIComponent(run.id)}`);
    } catch (e: any) {
      setErrorMsg(String(e?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-muted-foreground">
          Create a custom backtest by selecting strategies, setting weights, and choosing a date range. The system will simulate
          historical performance and show you the results.
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={equalizeWeights}
            disabled={!selected.length}
            className="btn"
          >
            Equalize weights
          </button>
          <button
            onClick={onRun}
            disabled={submitting}
            className="btn-primary"
          >
            {submitting ? "Creating run…" : "Run Backtest"}
          </button>
        </div>
      </div>

      {errorMsg ? (
        <div className="error-message mt-2.5">
          {errorMsg}
        </div>
      ) : null}

      {toast ? (
        <div className="fixed right-4 bottom-4 z-[9999] rounded-lg bg-foreground px-3 py-2.5 text-xs text-background">
          {toast}
        </div>
      ) : null}

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div className="grid gap-2.5">
          <label className="grid gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">Blend mode</span>
            <select value={mode} onChange={(e) => setMode(e.target.value as any)} className="input-field">
              <option value="nav_blend">Blend Returns (recommended for most users)</option>
              <option value="holdings_union">Combine Holdings (advanced)</option>
            </select>
            <span className="text-[11px] text-muted-foreground">
              {mode === "nav_blend" 
                ? "Combines strategy returns by weight. Simple and intuitive." 
                : "Merges actual holdings and rebalances together. More realistic but complex."}
            </span>
          </label>

          <div className="grid grid-cols-2 gap-2.5">
            <label className="grid gap-1.5">
              <span className="text-xs font-medium text-muted-foreground">Start date</span>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="input-field" />
            </label>
            <label className="grid gap-1.5">
              <span className="text-xs font-medium text-muted-foreground">End date</span>
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="input-field" />
            </label>
          </div>

          <label className="grid gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">Transaction cost (bps)</span>
            <input
              type="number"
              value={Number.isFinite(costBps) ? costBps : 0}
              min={0}
              step={0.5}
              onChange={(e) => setCostBps(Number(e.target.value))}
              className="input-field"
            />
            <span className="text-[11px] text-muted-foreground">
              Cost per trade. 10 bps = 0.1%. Set to 0 for idealized results.
            </span>
          </label>

          <label className="grid gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">Initial cash (USD)</span>
            <input
              type="number"
              value={Number.isFinite(initialCash) ? initialCash : 0}
              min={0}
              step={1000}
              onChange={(e) => setInitialCash(Number(e.target.value))}
              className="input-field"
            />
            <span className="text-[11px] text-muted-foreground">
              Starting portfolio value. Default: $100,000
            </span>
          </label>
        </div>

        <div className="rounded-lg border border-border bg-muted/30 p-2.5">
          <div className="mb-2 text-sm font-semibold">Selected strategies ({selected.length})</div>
          {selected.length ? (
            <div className="grid max-h-[220px] gap-2 overflow-auto pr-1.5">
              {selected.map((s) => (
                <div key={s.name} className="grid grid-cols-[1fr_120px_28px] items-center gap-2.5">
                  <div className="min-w-0">
                    <div className="overflow-hidden text-ellipsis whitespace-nowrap text-sm font-semibold">{s.name}</div>
                    <div className="text-[11px] text-muted-foreground">Weights auto-normalize to 100%</div>
                  </div>
                  <input
                    type="number"
                    value={Number.isFinite(s.weight) ? s.weight : 0}
                    min={0}
                    step={0.01}
                    onChange={(e) => setWeight(s.name, Number(e.target.value))}
                    className="input-field w-full text-xs"
                    placeholder="Weight"
                  />
                  <button
                    onClick={() => toggleStrategy(s.name)}
                    title="Remove"
                    className="btn h-7 w-7 p-0 text-lg leading-none"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-muted-foreground">Select strategies below to add them to your backtest.</div>
          )}
        </div>
      </div>

      <div className="mt-3">
        <div className="mb-2.5 flex flex-wrap items-center gap-2.5">
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Search strategies…"
            className="input-field min-w-[280px]"
          />
          <button
            onClick={() => {
              setSelected([]);
              setErrorMsg(null);
            }}
            className="btn"
          >
            Clear selection
          </button>
        </div>

        <div className="mb-2 text-xs text-muted-foreground">
          Select strategies to include in your backtest. You can adjust individual weights or use &quot;Equalize weights&quot; to distribute
          evenly.
        </div>

        <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-2.5">
          {options.map((opt) => {
            const checked = selectedSet.has(opt.name);
            return (
              <label
                key={opt.name}
                className={`cursor-pointer rounded-lg border border-border p-2.5 transition-colors hover:bg-accent/20 ${checked ? "border-primary/50 bg-accent/40" : "bg-card"}`}
              >
                <div className="flex items-start gap-2.5">
                  <input type="checkbox" checked={checked} onChange={() => toggleStrategy(opt.name)} className="mt-0.5" />
                  <div className="min-w-0">
                    <div className="overflow-hidden text-ellipsis whitespace-nowrap text-sm font-semibold">{opt.name}</div>
                    {opt.subcategory || opt.category ? (
                      <div className="text-[11px] text-muted-foreground">
                        {opt.subcategory || opt.category || ""}
                      </div>
                    ) : null}
                    {opt.description ? (
                      <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                        {opt.description}
                      </div>
                    ) : null}
                  </div>
                </div>
              </label>
            );
          })}
        </div>
      </div>
    </section>
  );
}
