"use client";

import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";

type SaveState = "idle" | "saving" | "saved" | "error";

type PortfolioOut = {
  id: string;
  name: string;
  description: string | null;
  default_cash: number;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

type AllocationTarget = "paper" | "live";

type AllocationRecord = {
  id: string;
  portfolio_id: string;
  amount: number;
  target: AllocationTarget;
  created_at: string;
  // allow backend to add fields without breaking UI
  [k: string]: unknown;
};

async function fetchJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const res = await fetch(input, init);
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`API error ${res.status}${txt ? `: ${txt}` : ""}`);
  }
  return (await res.json()) as T;
}

const inputStyle: CSSProperties = {
  padding: "8px 10px",
  borderRadius: 8,
  border: "1px solid #ddd",
};

const buttonStyle: CSSProperties = {
  padding: "8px 12px",
  borderRadius: 8,
  border: "1px solid #ddd",
  cursor: "pointer",
};

function formatUsd(n: number): string {
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(n);
}

export function AllocationsClient(props: { initialPortfolios: PortfolioOut[] }) {
  const [portfolios, setPortfolios] = useState<PortfolioOut[]>(props.initialPortfolios || []);
  const [portfolioId, setPortfolioId] = useState<string>(() => props.initialPortfolios?.[0]?.id ?? "");
  const [target, setTarget] = useState<AllocationTarget>("paper");
  const [amountText, setAmountText] = useState<string>("1000");

  const [history, setHistory] = useState<AllocationRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [infoMsg, setInfoMsg] = useState<string | null>(null);

  const selectedPortfolio = useMemo(() => portfolios.find((p) => p.id === portfolioId) || null, [portfolios, portfolioId]);

  const currentAllocated = useMemo(() => {
    return history.reduce((sum, r) => sum + (Number.isFinite(Number(r.amount)) ? Number(r.amount) : 0), 0);
  }, [history]);

  async function refreshPortfolios() {
    const data = await fetchJson<PortfolioOut[]>("/api/portfolios", { cache: "no-store" });
    setPortfolios(data);
    if (portfolioId && !data.some((p) => p.id === portfolioId)) {
      setPortfolioId(data[0]?.id ?? "");
    }
  }

  async function loadHistory() {
    if (!portfolioId) {
      setHistory([]);
      return;
    }
    setLoading(true);
    setErrorMsg(null);
    setInfoMsg(null);
    try {
      // Expected from Agent E:
      // GET /allocations?portfolio_id=<uuid>&target=paper|live => AllocationRecord[]
      const qs = new URLSearchParams({ portfolio_id: portfolioId, target });
      const rows = await fetchJson<AllocationRecord[]>(`/api/allocations?${qs.toString()}`, { cache: "no-store" });
      setHistory(Array.isArray(rows) ? rows : []);
    } catch (e: any) {
      const msg = String(e?.message || e);
      setHistory([]);
      setErrorMsg(
        msg +
          " (If this says 404, the allocation-ledger endpoints may not be deployed yet. Once they are, this page will show allocation history and current allocated amount.)",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshPortfolios().catch(() => {
      // ignore; SSR provided initial list
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadHistory().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [portfolioId, target]);

  async function onCreateAllocation() {
    setErrorMsg(null);
    setInfoMsg(null);
    setSaveState("saving");
    const amt = Number(amountText);
    if (!portfolioId) {
      setSaveState("error");
      setErrorMsg("Pick a portfolio first.");
      return;
    }
    if (!Number.isFinite(amt) || amt === 0) {
      setSaveState("error");
      setErrorMsg("Amount must be a non-zero number (positive to allocate, negative to de-allocate).");
      return;
    }
    try {
      // Expected from Agent E:
      // POST /allocations { portfolio_id, amount, target } => AllocationRecord
      await fetchJson<AllocationRecord>("/api/allocations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ portfolio_id: portfolioId, amount: amt, target }),
      });
      setSaveState("saved");
      setInfoMsg("Allocation recorded.");
      await loadHistory();
    } catch (e: any) {
      setSaveState("error");
      setErrorMsg(String(e?.message || e));
    }
  }

  return (
    <main style={{ padding: 20, maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: "8px 0 6px" }}>Allocations</h2>
          <div style={{ color: "#666", fontSize: 12 }}>
            Send +$X to a portfolio (or -$X to withdraw) and track the allocation ledger.
          </div>
        </div>
        <button onClick={() => refreshPortfolios().catch((e) => setErrorMsg(String(e?.message || e)))} style={buttonStyle}>
          Refresh portfolios
        </button>
      </div>

      {errorMsg ? (
        <div
          style={{
            background: "#fff3f3",
            border: "1px solid #f3b0b0",
            padding: 10,
            borderRadius: 8,
            marginTop: 12,
            color: "#b00020",
            whiteSpace: "pre-wrap",
          }}
        >
          {errorMsg}
        </div>
      ) : null}
      {infoMsg ? (
        <div
          style={{
            background: "#f6ffed",
            border: "1px solid #b7eb8f",
            padding: 10,
            borderRadius: 8,
            marginTop: 12,
            color: "#135200",
          }}
        >
          {infoMsg}
        </div>
      ) : null}

      <div style={{ marginTop: 12, border: "1px solid #eee", borderRadius: 10, overflow: "hidden" }}>
        <div style={{ padding: 10, background: "#fafafa", borderBottom: "1px solid #eee", fontWeight: 600 }}>
          Create allocation
        </div>
        <div style={{ padding: 12, display: "grid", gridTemplateColumns: "1fr 180px 180px 180px", gap: 10, alignItems: "end" }}>
          <div>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>Portfolio</div>
            <select value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)} style={{ ...inputStyle, width: "100%" }}>
              <option value="" disabled>
                Select…
              </option>
              {portfolios.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            {selectedPortfolio ? (
              <div style={{ fontSize: 12, color: "#666", marginTop: 6 }}>
                Default cash: {formatUsd(Number(selectedPortfolio.default_cash ?? 0))}
              </div>
            ) : null}
          </div>

          <div>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>Target</div>
            <select value={target} onChange={(e) => setTarget(e.target.value as AllocationTarget)} style={{ ...inputStyle, width: "100%" }}>
              <option value="paper">paper</option>
              <option value="live">live</option>
            </select>
          </div>

          <div>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>Amount</div>
            <input
              value={amountText}
              onChange={(e) => {
                setAmountText(e.target.value);
                setSaveState("idle");
              }}
              placeholder="e.g. 25000"
              inputMode="decimal"
              style={{ ...inputStyle, width: "100%" }}
            />
          </div>

          <div>
            <button onClick={onCreateAllocation} disabled={saveState === "saving"} style={{ ...buttonStyle, width: "100%" }}>
              {saveState === "saving" ? "Submitting…" : "Submit"}
            </button>
            <div style={{ fontSize: 12, color: "#666", marginTop: 6, minHeight: 16 }}>
              {saveState === "saved" ? "Saved" : saveState === "error" ? "Error" : ""}
            </div>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 12, display: "flex", gap: 12, flexWrap: "wrap" }}>
        <div style={{ padding: "10px 12px", border: "1px solid #eee", borderRadius: 10 }}>
          <div style={{ fontSize: 11, color: "#666", textTransform: "uppercase" }}>Current allocated</div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>{formatUsd(currentAllocated)}</div>
          <div style={{ fontSize: 12, color: "#666" }}>Computed as sum(history) for selected portfolio + target.</div>
        </div>
        <button onClick={() => loadHistory().catch((e) => setErrorMsg(String(e?.message || e)))} style={buttonStyle}>
          Reload history
        </button>
      </div>

      <div style={{ marginTop: 12, overflowX: "auto", border: "1px solid #eee", borderRadius: 12 }}>
        <div style={{ padding: 10, background: "#fafafa", borderBottom: "1px solid #eee", fontWeight: 600 }}>
          Allocation history {loading ? "— loading…" : ""}
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#fafafa" }}>
              <th style={{ textAlign: "left", padding: 10, borderBottom: "1px solid #eee" }}>When</th>
              <th style={{ textAlign: "left", padding: 10, borderBottom: "1px solid #eee" }}>Target</th>
              <th style={{ textAlign: "right", padding: 10, borderBottom: "1px solid #eee" }}>Amount</th>
              <th style={{ textAlign: "left", padding: 10, borderBottom: "1px solid #eee" }}>Allocation id</th>
            </tr>
          </thead>
          <tbody>
            {history.map((r) => (
              <tr key={String(r.id)}>
                <td style={{ padding: 10, borderBottom: "1px solid #f1f1f1" }}>
                  {r.created_at ? new Date(String(r.created_at)).toLocaleString() : "—"}
                </td>
                <td style={{ padding: 10, borderBottom: "1px solid #f1f1f1" }}>{String(r.target)}</td>
                <td style={{ padding: 10, borderBottom: "1px solid #f1f1f1", textAlign: "right" }}>
                  {formatUsd(Number(r.amount ?? 0))}
                </td>
                <td style={{ padding: 10, borderBottom: "1px solid #f1f1f1", fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" }}>
                  {String(r.id)}
                </td>
              </tr>
            ))}
            {history.length === 0 && !loading ? (
              <tr>
                <td colSpan={4} style={{ padding: 12, color: "#666" }}>
                  No allocation records for this selection.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </main>
  );
}

