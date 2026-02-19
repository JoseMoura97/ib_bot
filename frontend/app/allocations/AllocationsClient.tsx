"use client";

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

type AllocationMode = "paper" | "live";

type AllocationRecord = {
  id: string;
  portfolio_id: string;
  amount: number;
  mode: AllocationMode;
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

// Styles migrated to CSS classes for dark mode support

function formatUsd(n: number): string {
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(n);
}

export function AllocationsClient(props: { initialPortfolios: PortfolioOut[] }) {
  const [portfolios, setPortfolios] = useState<PortfolioOut[]>(props.initialPortfolios || []);
  const [portfolioId, setPortfolioId] = useState<string>(() => props.initialPortfolios?.[0]?.id ?? "");
  const [mode, setMode] = useState<AllocationMode>("paper");
  const [accountId, setAccountId] = useState<string>("paper");
  const [amountText, setAmountText] = useState<string>("1000");

  const [history, setHistory] = useState<AllocationRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [infoMsg, setInfoMsg] = useState<string | null>(null);

  const selectedPortfolio = useMemo(() => portfolios.find((p) => p.id === portfolioId) || null, [portfolios, portfolioId]);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("allocations.accountId");
      if (saved) setAccountId(saved);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem("allocations.accountId", accountId);
    } catch {
      // ignore
    }
  }, [accountId]);

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
      const qs = new URLSearchParams({ portfolio_id: portfolioId });
      const rows = await fetchJson<AllocationRecord[]>(`/api/allocations?${qs.toString()}`, { cache: "no-store" });
      setHistory(Array.isArray(rows) ? rows : []);
    } catch (e: any) {
      const msg = String(e?.message || e);
      setHistory([]);
      setErrorMsg(
        msg +
          " (If this says 404, the allocation endpoints may not be deployed yet. Once they are, this page will show allocation history and current allocated amount.)",
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
  }, [portfolioId]);

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
    if (!Number.isFinite(amt) || amt <= 0) {
      setSaveState("error");
      setErrorMsg("Amount must be a positive number.");
      return;
    }
    try {
      await fetchJson<AllocationRecord>("/api/allocations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ portfolio_id: portfolioId, amount: amt, mode, account_id: accountId }),
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
    <main className="mx-auto max-w-[1200px] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="mb-1.5 mt-2">Allocations</h2>
          <div className="text-xs text-muted-foreground">
            Allocate cash to a portfolio and track the allocation ledger.
          </div>
        </div>
        <button onClick={() => refreshPortfolios().catch((e) => setErrorMsg(String(e?.message || e)))} className="btn">
          Refresh portfolios
        </button>
      </div>

      {errorMsg ? (
        <div className="error-message mt-3 whitespace-pre-wrap">
          {errorMsg}
        </div>
      ) : null}
      {infoMsg ? (
        <div className="info-message mt-3">
          {infoMsg}
        </div>
      ) : null}

      <div className="section-card mt-3 overflow-hidden">
        <div className="section-header">
          Create allocation
        </div>
        <div className="grid items-end gap-2.5 p-3 lg:grid-cols-[1fr_180px_180px_180px_200px]">
          <div>
            <div className="mb-1.5 text-xs text-muted-foreground">Portfolio</div>
            <select value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)} className="input-field w-full">
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
              <div className="mt-1.5 text-xs text-muted-foreground">
                Default cash: {formatUsd(Number(selectedPortfolio.default_cash ?? 0))}
              </div>
            ) : null}
          </div>

          <div>
            <div className="mb-1.5 text-xs text-muted-foreground">Mode</div>
            <select value={mode} onChange={(e) => setMode(e.target.value as AllocationMode)} className="input-field w-full">
              <option value="paper">paper</option>
              <option value="live">live</option>
            </select>
          </div>

          <div>
            <div className="mb-1.5 text-xs text-muted-foreground">Amount</div>
            <input
              value={amountText}
              onChange={(e) => {
                setAmountText(e.target.value);
                setSaveState("idle");
              }}
              placeholder="e.g. 25000"
              inputMode="decimal"
              className="input-field w-full"
            />
          </div>

          <div>
            <div className="mb-1.5 text-xs text-muted-foreground">Account ID</div>
            <input
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              placeholder="e.g. paper-1"
              className="input-field w-full"
            />
          </div>

          <div>
            <button onClick={onCreateAllocation} disabled={saveState === "saving"} className="btn w-full">
              {saveState === "saving" ? "Submitting…" : "Submit"}
            </button>
            <div className="mt-1.5 min-h-[16px] text-xs text-muted-foreground">
              {saveState === "saved" ? "Saved" : saveState === "error" ? "Error" : ""}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-3">
        <div className="stat-card">
          <div className="stat-label">Current allocated</div>
          <div className="stat-value">{formatUsd(currentAllocated)}</div>
          <div className="text-xs text-muted-foreground">Computed as sum(history) for selected portfolio.</div>
        </div>
        <button onClick={() => loadHistory().catch((e) => setErrorMsg(String(e?.message || e)))} className="btn">
          Reload history
        </button>
      </div>

      <div className="section-card mt-3 overflow-x-auto">
        <div className="section-header">
          Allocation history {loading ? "— loading…" : ""}
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>When</th>
              <th>Mode</th>
              <th className="text-right">Amount</th>
              <th>Allocation id</th>
            </tr>
          </thead>
          <tbody>
            {history.map((r) => (
              <tr key={String(r.id)}>
                <td>
                  {r.created_at ? new Date(String(r.created_at)).toLocaleString() : "—"}
                </td>
                <td>{String(r.mode)}</td>
                <td className="text-right">
                  {formatUsd(Number(r.amount ?? 0))}
                </td>
                <td className="font-mono">
                  {String(r.id)}
                </td>
              </tr>
            ))}
            {history.length === 0 && !loading ? (
              <tr>
                <td colSpan={4} className="empty-state">
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

