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
    <section style={{ border: "1px solid #eee", borderRadius: 12, padding: 14, background: "white" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h3 style={{ margin: "4px 0 6px" }}>Backtest Wizard</h3>
          <div style={{ fontSize: 12, color: "#666" }}>
            Pick 1+ strategies + weights, choose blend mode, date range, and transaction cost. “Run” will create a run and open run details.
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <button
            onClick={equalizeWeights}
            disabled={!selected.length}
            style={{
              padding: "8px 10px",
              borderRadius: 8,
              border: "1px solid #ddd",
              cursor: selected.length ? "pointer" : "not-allowed",
            }}
          >
            Equalize weights
          </button>
          <button
            onClick={onRun}
            disabled={submitting}
            style={{
              padding: "8px 12px",
              borderRadius: 8,
              border: "1px solid #ddd",
              cursor: submitting ? "not-allowed" : "pointer",
              background: "#eef6ff",
            }}
          >
            {submitting ? "Creating run…" : "Run"}
          </button>
        </div>
      </div>

      {errorMsg ? (
        <div
          style={{
            marginTop: 10,
            background: "#fff3f3",
            border: "1px solid #f3b0b0",
            padding: 10,
            borderRadius: 8,
            color: "#b00020",
          }}
        >
          {errorMsg}
        </div>
      ) : null}

      {toast ? (
        <div
          style={{
            position: "fixed",
            right: 16,
            bottom: 16,
            background: "#111",
            color: "white",
            padding: "10px 12px",
            borderRadius: 10,
            fontSize: 12,
            zIndex: 9999,
          }}
        >
          {toast}
        </div>
      ) : null}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
        <div style={{ display: "grid", gap: 10 }}>
          <label style={{ display: "grid", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#666" }}>Blend mode</span>
            <select value={mode} onChange={(e) => setMode(e.target.value as any)} style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #ddd" }}>
              <option value="nav_blend">nav_blend (blend equity curves by weights)</option>
              <option value="holdings_union">holdings_union (union rebalance events, combine holdings)</option>
            </select>
          </label>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <label style={{ display: "grid", gap: 6 }}>
              <span style={{ fontSize: 12, color: "#666" }}>Start date</span>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #ddd" }} />
            </label>
            <label style={{ display: "grid", gap: 6 }}>
              <span style={{ fontSize: 12, color: "#666" }}>End date</span>
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #ddd" }} />
            </label>
          </div>

          <label style={{ display: "grid", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#666" }}>Transaction cost (bps)</span>
            <input
              type="number"
              value={Number.isFinite(costBps) ? costBps : 0}
              min={0}
              step={0.5}
              onChange={(e) => setCostBps(Number(e.target.value))}
              style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #ddd" }}
            />
          </label>

          <label style={{ display: "grid", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#666" }}>Initial cash (USD)</span>
            <input
              type="number"
              value={Number.isFinite(initialCash) ? initialCash : 0}
              min={0}
              step={1000}
              onChange={(e) => setInitialCash(Number(e.target.value))}
              style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #ddd" }}
            />
          </label>
        </div>

        <div style={{ border: "1px solid #eee", borderRadius: 10, padding: 10, background: "#fafafa" }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>Selected strategies ({selected.length})</div>
          {selected.length ? (
            <div style={{ display: "grid", gap: 8, maxHeight: 220, overflow: "auto", paddingRight: 6 }}>
              {selected.map((s) => (
                <div key={s.name} style={{ display: "grid", gridTemplateColumns: "1fr 120px 28px", gap: 10, alignItems: "center" }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.name}</div>
                    <div style={{ fontSize: 11, color: "#666" }}>Weight is normalized on submit</div>
                  </div>
                  <input
                    type="number"
                    value={Number.isFinite(s.weight) ? s.weight : 0}
                    min={0}
                    step={0.01}
                    onChange={(e) => setWeight(s.name, Number(e.target.value))}
                    style={{ padding: "6px 8px", borderRadius: 8, border: "1px solid #ddd", width: "100%" }}
                  />
                  <button
                    onClick={() => toggleStrategy(s.name)}
                    title="Remove"
                    style={{ width: 28, height: 28, borderRadius: 8, border: "1px solid #ddd", background: "white", cursor: "pointer" }}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: "#666", fontSize: 12 }}>Select strategies below.</div>
          )}
        </div>
      </div>

      <div style={{ marginTop: 12 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 10, flexWrap: "wrap" }}>
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Search strategies…"
            style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #ddd", minWidth: 280 }}
          />
          <button
            onClick={() => {
              setSelected([]);
              setErrorMsg(null);
            }}
            style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #ddd", cursor: "pointer" }}
          >
            Clear selection
          </button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 10 }}>
          {options.map((opt) => {
            const checked = selectedSet.has(opt.name);
            return (
              <label
                key={opt.name}
                style={{
                  border: "1px solid #eee",
                  borderRadius: 10,
                  padding: 10,
                  cursor: "pointer",
                  background: checked ? "#eef6ff" : "white",
                }}
              >
                <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <input type="checkbox" checked={checked} onChange={() => toggleStrategy(opt.name)} />
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{opt.name}</div>
                    {opt.subcategory || opt.category ? (
                      <div style={{ fontSize: 11, color: "#777" }}>
                        {opt.category ? `${opt.category} / ` : ""}
                        {opt.subcategory || ""}
                      </div>
                    ) : null}
                    {opt.description ? (
                      <div style={{ fontSize: 12, color: "#666", marginTop: 4, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" as any }}>
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

