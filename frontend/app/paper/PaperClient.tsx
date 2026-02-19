"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { PaperAccount, PaperBalance, PaperFill, PaperOrder, PaperOrderSide, PaperPosition } from "./_lib/paperApi";
import {
  fundPaperAccount,
  getPaperSummary,
  listPaperAccounts,
  listPaperFills,
  listPaperOrders,
  listPaperPositions,
  listPortfolios,
  paperRebalanceExecute,
  paperRebalancePreview,
  placePaperMarketOrder,
} from "./_lib/paperApi";

function fmtMoney(n: number | undefined, currency = "USD"): string {
  if (n == null || !Number.isFinite(n)) return "—";
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(n);
  } catch {
    return `${n.toFixed(2)} ${currency}`;
  }
}

function fmtNum(n: number | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toFixed(digits);
}

function fmtTime(s: string | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString();
}

function clampPositive(n: number): number {
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, n);
}

export function PaperClient() {
  const [accounts, setAccounts] = useState<PaperAccount[]>([]);
  const [accountId, setAccountId] = useState<string>("default");

  const [balance, setBalance] = useState<PaperBalance | null>(null);
  const [positions, setPositions] = useState<PaperPosition[]>([]);
  const [orders, setOrders] = useState<PaperOrder[]>([]);
  const [fills, setFills] = useState<PaperFill[]>([]);

  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [fundAmount, setFundAmount] = useState<string>("10000");

  const [symbol, setSymbol] = useState("AAPL");
  const [side, setSide] = useState<PaperOrderSide>("BUY");
  const [qty, setQty] = useState<string>("1");

  // Optional: allocate cash to a portfolio (rebalance-to-target)
  const [portfolios, setPortfolios] = useState<{ id: string; name: string }[]>([]);
  const [portfolioId, setPortfolioId] = useState<string>("");
  const [allocationUsd, setAllocationUsd] = useState<string>("10000");
  const [rebalancePreview, setRebalancePreview] = useState<any>(null);
  const [rebalanceError, setRebalanceError] = useState<string | null>(null);

  // P&L / Performance tracking
  type PnlDaily = { date: string; equity: number; cash: number; daily_pnl: number; cumulative_pnl: number };
  type PnlSummary = { total_return: number; total_pnl: number; max_drawdown: number; days: number; first_equity: number; last_equity: number };
  const [pnlDaily, setPnlDaily] = useState<PnlDaily[]>([]);
  const [pnlSummary, setPnlSummary] = useState<PnlSummary | null>(null);
  const [pnlLoading, setPnlLoading] = useState(false);
  type RebalLog = { id: number; timestamp: string; portfolio_id: string; status: string; n_orders: number; details: any };
  const [rebalLogs, setRebalLogs] = useState<RebalLog[]>([]);

  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  async function refreshAll(targetAccountId: string): Promise<{
    balance: PaperBalance | null;
    positions: PaperPosition[];
    orders: PaperOrder[];
    fills: PaperFill[];
  } | null> {
    setError(null);
    const aid = targetAccountId || "default";
    try {
      const [summary, pos, ord, fil] = await Promise.all([
        getPaperSummary(aid),
        listPaperPositions(aid),
        listPaperOrders(aid, 50),
        listPaperFills(aid, 50),
      ]);
      if (!mountedRef.current) return;
      setBalance(summary.balance);
      setPositions(pos.length ? pos : summary.positions);
      setOrders(ord);
      setFills(fil);
      return { balance: summary.balance, positions: pos.length ? pos : summary.positions, orders: ord, fills: fil };
    } catch (e: any) {
      if (!mountedRef.current) return;
      setError(String(e?.message || e));
      return null;
    }
  }

  async function refreshPnl(aid: string) {
    setPnlLoading(true);
    try {
      const [pnlRes, logsRes] = await Promise.all([
        fetch(`/api/paper/accounts/${encodeURIComponent(aid)}/pnl`).then((r) => r.json()),
        fetch(`/api/paper/accounts/${encodeURIComponent(aid)}/rebalance-logs?limit=20`).then((r) => r.json()),
      ]);
      if (!mountedRef.current) return;
      setPnlDaily(pnlRes?.daily ?? []);
      setPnlSummary(pnlRes?.summary ?? null);
      setRebalLogs(logsRes ?? []);
    } catch {
      // best-effort
    } finally {
      if (mountedRef.current) setPnlLoading(false);
    }
  }

  useEffect(() => {
    async function boot() {
      setLoading(true);
      setError(null);
      try {
        const acct = await listPaperAccounts();
        if (!mountedRef.current) return;
        setAccounts(acct);
        const firstId = acct[0]?.id || "default";
        setAccountId(firstId);
        await refreshAll(firstId);
        refreshPnl(firstId).catch(() => {});
      } catch (e: any) {
        if (!mountedRef.current) return;
        setError(String(e?.message || e));
      } finally {
        if (mountedRef.current) setLoading(false);
      }
    }
    boot();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // Best-effort load of portfolios for optional rebalance section
    listPortfolios()
      .then((p) => {
        if (!mountedRef.current) return;
        setPortfolios(p);
        if (!portfolioId && p[0]?.id) setPortfolioId(p[0].id);
      })
      .catch(() => {
        // ignore
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const currency = balance?.currency || accounts.find((a) => a.id === accountId)?.currency || "USD";
  const cash = balance?.cash;
  const equity = balance?.equity;

  const computedEquity = useMemo(() => {
    if (equity != null && Number.isFinite(equity)) return equity;
    const cashPart = cash != null && Number.isFinite(cash) ? cash : 0;
    const mv = positions.reduce((acc, p) => acc + (p.market_value ?? (p.market_price != null ? p.market_price * p.quantity : 0)), 0);
    return cashPart + mv;
  }, [cash, equity, positions]);

  async function onAccountChange(nextId: string) {
    setAccountId(nextId);
    setRebalancePreview(null);
    setRebalanceError(null);
    setLoading(true);
    try {
      await refreshAll(nextId);
      refreshPnl(nextId).catch(() => {});
    } finally {
      setLoading(false);
    }
  }

  async function onFund() {
    const amt = clampPositive(Number(fundAmount));
    if (!amt) return;
    setActionBusy("fund");
    setError(null);
    try {
      await fundPaperAccount({ accountId, amount: amt, currency });
      await refreshAll(accountId);
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setActionBusy(null);
    }
  }

  async function onSubmitOrder() {
    const q = clampPositive(Number(qty));
    const sym = (symbol || "").trim().toUpperCase();
    if (!sym || !q) return;

    setActionBusy("order");
    setError(null);
    const submittedAt = new Date();
    try {
      await placePaperMarketOrder({ accountId, symbol: sym, side, quantity: q });

      // Refresh a few times so immediate fills show up without manual clicks.
      for (let i = 0; i < 6; i++) {
        // eslint-disable-next-line no-await-in-loop
        const snap = await refreshAll(accountId);
        const newestFill = snap?.fills?.[0];
        const newestTs = newestFill?.timestamp ? new Date(newestFill.timestamp) : null;
        if (newestFill?.symbol === sym && newestTs && newestTs >= submittedAt) break;
        // eslint-disable-next-line no-await-in-loop
        await new Promise((r) => setTimeout(r, 650));
      }
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setActionBusy(null);
    }
  }

  async function onPreviewRebalance() {
    const amt = clampPositive(Number(allocationUsd));
    if (!portfolioId || !amt) return;
    setRebalanceError(null);
    setRebalancePreview(null);
    setActionBusy("preview");
    try {
      const preview = await paperRebalancePreview({ accountId, portfolioId, allocationUsd: amt });
      setRebalancePreview(preview);
    } catch (e: any) {
      setRebalanceError(String(e?.message || e));
    } finally {
      setActionBusy(null);
    }
  }

  async function onExecuteRebalance() {
    const amt = clampPositive(Number(allocationUsd));
    if (!portfolioId || !amt) return;
    setRebalanceError(null);
    setActionBusy("execute");
    try {
      const out = await paperRebalanceExecute({ accountId, portfolioId, allocationUsd: amt });
      setRebalancePreview(out);
      await refreshAll(accountId);
    } catch (e: any) {
      setRebalanceError(String(e?.message || e));
    } finally {
      setActionBusy(null);
    }
  }

  if (loading && !balance && positions.length === 0 && fills.length === 0) {
    return <div className="p-5">Loading paper trading…</div>;
  }

  return (
    <main className="mx-auto max-w-[1400px] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="mb-1.5 mt-2">Paper Trading</h2>
          <div className="text-xs text-muted-foreground">Place a market order and watch cash/positions update instantly.</div>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <label className="text-xs text-muted-foreground">
            Account{" "}
            <select
              value={accountId}
              onChange={(e) => onAccountChange(e.target.value)}
              className="input-field ml-1.5 inline-block"
            >
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name ? `${a.name} (${a.id})` : a.id}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={() => refreshAll(accountId)}
            className="btn"
            disabled={!!actionBusy}
          >
            Refresh
          </button>
        </div>
      </div>

      {error ? (
        <div className="error-message mt-3">
          {error}
        </div>
      ) : null}

      <div className="mt-3.5 flex flex-wrap gap-3">
        <div className="stat-card">
          <div className="stat-label">Cash</div>
          <div className="stat-value">{fmtMoney(cash, currency)}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Equity</div>
          <div className="stat-value">{fmtMoney(computedEquity, currency)}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Positions</div>
          <div className="stat-value">{positions.length}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Last update</div>
          <div className="text-xs font-semibold">{fmtTime(balance?.updated_at)}</div>
        </div>
      </div>

      <div className="mt-3.5 grid gap-3 lg:grid-cols-[420px_1fr]">
        <div className="section-card p-3">
          <h3 className="mb-2.5 mt-0">Fund paper account</h3>
          <div className="flex flex-wrap items-center gap-2.5">
            <input
              value={fundAmount}
              onChange={(e) => setFundAmount(e.target.value)}
              inputMode="decimal"
              placeholder="Amount"
              className="input-field w-40"
            />
            <span className="text-xs text-muted-foreground">{currency}</span>
            <button
              onClick={onFund}
              disabled={actionBusy === "fund"}
              className="btn"
            >
              {actionBusy === "fund" ? "Funding…" : "Add cash"}
            </button>
          </div>
          <div className="mt-2 text-xs text-muted-foreground">
            Uses Agent E funding endpoint if available; otherwise shows a clear error.
          </div>
        </div>

        <div className="section-card p-3">
          <h3 className="mb-2.5 mt-0">Order ticket (market)</h3>
          <div className="flex flex-wrap items-center gap-2.5">
            <input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="Symbol (e.g. AAPL)"
              className="input-field w-40"
            />
            <select value={side} onChange={(e) => setSide(e.target.value as PaperOrderSide)} className="input-field">
              <option value="BUY">BUY</option>
              <option value="SELL">SELL</option>
            </select>
            <input
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              inputMode="decimal"
              placeholder="Qty"
              className="input-field w-30"
            />
            <button
              onClick={onSubmitOrder}
              disabled={actionBusy === "order"}
              className="btn"
            >
              {actionBusy === "order" ? "Submitting…" : "Submit"}
            </button>
          </div>
          <div className="mt-2 text-xs text-muted-foreground">
            After submit, this page auto-refreshes to show the fill and updated cash/positions.
          </div>
        </div>
      </div>

      <div className="mt-3.5 grid gap-3 lg:grid-cols-2">
        <div className="section-card overflow-hidden">
          <div className="section-header">Positions</div>
          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Qty</th>
                  <th>Avg cost</th>
                  <th>Mkt price</th>
                  <th>Mkt value</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={p.symbol}>
                    <td className="font-bold">{p.symbol}</td>
                    <td>{fmtNum(p.quantity, 4)}</td>
                    <td>{fmtMoney(p.avg_cost, p.currency || currency)}</td>
                    <td>{fmtMoney(p.market_price, p.currency || currency)}</td>
                    <td>
                      {fmtMoney(p.market_value ?? (p.market_price != null ? p.market_price * p.quantity : undefined), p.currency || currency)}
                    </td>
                  </tr>
                ))}
                {positions.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="empty-state">
                      No positions.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>

        <div className="section-card overflow-hidden">
          <div className="section-header">Recent fills / trades</div>
          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Qty</th>
                  <th>Price</th>
                </tr>
              </thead>
              <tbody>
                {fills.map((f, idx) => (
                  <tr key={`${f.id ?? "fill"}-${idx}`}>
                    <td className="text-xs">{fmtTime(f.timestamp)}</td>
                    <td className="font-bold">{f.symbol}</td>
                    <td>{f.side}</td>
                    <td>{fmtNum(f.quantity, 4)}</td>
                    <td>{fmtMoney(f.price, currency)}</td>
                  </tr>
                ))}
                {fills.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="empty-state">
                      No fills yet.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="section-card mt-3.5 overflow-hidden">
        <div className="section-header">Recent orders</div>
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Qty</th>
                <th>Type</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o, idx) => (
                <tr key={`${o.id ?? "order"}-${idx}`}>
                  <td className="text-xs">{fmtTime(o.created_at)}</td>
                  <td className="font-bold">{o.symbol}</td>
                  <td>{o.side}</td>
                  <td>{fmtNum(o.quantity, 4)}</td>
                  <td>{o.type || "—"}</td>
                  <td>{o.status || "—"}</td>
                </tr>
              ))}
              {orders.length === 0 ? (
                <tr>
                  <td colSpan={6} className="empty-state">
                    No orders yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      {portfolios.length ? (
        <div className="section-card mt-3.5 p-3">
          <h3 className="mb-2.5 mt-0">Optional: Allocate cash to a portfolio (rebalance)</h3>
          <div className="flex flex-wrap items-center gap-2.5">
            <select
              value={portfolioId}
              onChange={(e) => setPortfolioId(e.target.value)}
              className="input-field min-w-[260px]"
            >
              {portfolios.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <input
              value={allocationUsd}
              onChange={(e) => setAllocationUsd(e.target.value)}
              inputMode="decimal"
              placeholder="Allocation (USD)"
              className="input-field w-[200px]"
            />
            <button
              onClick={onPreviewRebalance}
              disabled={actionBusy === "preview"}
              className="btn"
            >
              {actionBusy === "preview" ? "Previewing…" : "Preview"}
            </button>
            <button
              onClick={onExecuteRebalance}
              disabled={actionBusy === "execute"}
              className="btn"
            >
              {actionBusy === "execute" ? "Executing…" : "Execute"}
            </button>
          </div>
          {rebalanceError ? (
            <div className="error-message mt-2.5">
              {rebalanceError}
            </div>
          ) : null}
          {rebalancePreview ? (
            <pre className="code-block">
              {JSON.stringify(rebalancePreview, null, 2)}
            </pre>
          ) : null}
        </div>
      ) : null}

      {/* P&L / Performance Tracking */}
      <div className="section-card mt-3.5 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5">
          <h3 className="mt-0 mb-0">Performance Tracking</h3>
          <button onClick={() => refreshPnl(accountId)} disabled={pnlLoading} className="btn text-xs">
            {pnlLoading ? "Loading..." : "Refresh P&L"}
          </button>
        </div>

        {pnlSummary && pnlSummary.days > 0 ? (
          <>
            <div className="flex flex-wrap gap-3 mb-3">
              <div className="stat-card">
                <div className="stat-label">Total P&L</div>
                <div className={`stat-value ${pnlSummary.total_pnl >= 0 ? "text-emerald-600" : "text-red-500"}`}>
                  {fmtMoney(pnlSummary.total_pnl)}
                </div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Total Return</div>
                <div className={`stat-value ${pnlSummary.total_return >= 0 ? "text-emerald-600" : "text-red-500"}`}>
                  {(pnlSummary.total_return * 100).toFixed(2)}%
                </div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Max Drawdown</div>
                <div className="stat-value text-red-500">{(pnlSummary.max_drawdown * 100).toFixed(2)}%</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Days Tracked</div>
                <div className="stat-value">{pnlSummary.days}</div>
              </div>
            </div>

            {/* Equity curve SVG sparkline */}
            {pnlDaily.length > 1 ? (
              <div className="mb-3">
                <div className="text-xs font-semibold mb-1">Equity Curve</div>
                <svg viewBox={`0 0 ${Math.max(pnlDaily.length - 1, 1)} 100`} className="w-full h-32 border rounded bg-background" preserveAspectRatio="none">
                  {(() => {
                    const eqs = pnlDaily.map((d) => d.equity);
                    const minE = Math.min(...eqs);
                    const maxE = Math.max(...eqs);
                    const range = maxE - minE || 1;
                    const points = eqs.map((e, i) => `${i},${100 - ((e - minE) / range) * 90 - 5}`).join(" ");
                    return <polyline points={points} fill="none" stroke="currentColor" strokeWidth="0.5" className="text-emerald-500" />;
                  })()}
                </svg>
                <div className="flex justify-between text-[10px] text-muted-foreground mt-0.5">
                  <span>{pnlDaily[0]?.date}</span>
                  <span>{pnlDaily[pnlDaily.length - 1]?.date}</span>
                </div>
              </div>
            ) : null}

            {/* Daily P&L bars */}
            {pnlDaily.length > 1 ? (
              <div className="mb-3">
                <div className="text-xs font-semibold mb-1">Daily P&L</div>
                <div className="flex items-end gap-px h-20 border rounded bg-background p-1 overflow-hidden">
                  {pnlDaily.slice(1).map((d, i) => {
                    const maxPnl = Math.max(...pnlDaily.slice(1).map((x) => Math.abs(x.daily_pnl)), 1);
                    const pct = Math.abs(d.daily_pnl) / maxPnl;
                    return (
                      <div
                        key={i}
                        className={`flex-1 min-w-[1px] ${d.daily_pnl >= 0 ? "bg-emerald-500" : "bg-red-500"}`}
                        style={{
                          height: `${Math.max(pct * 100, 2)}%`,
                          alignSelf: d.daily_pnl >= 0 ? "flex-end" : "flex-end",
                          opacity: 0.8,
                        }}
                        title={`${d.date}: ${fmtMoney(d.daily_pnl)}`}
                      />
                    );
                  })}
                </div>
              </div>
            ) : null}

            {/* Daily data table */}
            <details className="mb-2">
              <summary className="text-xs font-semibold cursor-pointer">Daily breakdown ({pnlDaily.length} entries)</summary>
              <div className="table-wrapper mt-1">
                <table className="data-table text-xs">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Equity</th>
                      <th>Cash</th>
                      <th>Daily P&L</th>
                      <th>Cumulative</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pnlDaily.map((d, i) => (
                      <tr key={i}>
                        <td>{d.date}</td>
                        <td>{fmtMoney(d.equity)}</td>
                        <td>{fmtMoney(d.cash)}</td>
                        <td className={d.daily_pnl >= 0 ? "text-emerald-600" : "text-red-500"}>{fmtMoney(d.daily_pnl)}</td>
                        <td className={d.cumulative_pnl >= 0 ? "text-emerald-600" : "text-red-500"}>{fmtMoney(d.cumulative_pnl)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </>
        ) : (
          <div className="text-xs text-muted-foreground">
            No snapshots yet. Snapshots are taken daily at 4:30 PM ET by the automated scheduler.
          </div>
        )}

        {/* Rebalance logs */}
        {rebalLogs.length > 0 ? (
          <details className="mt-2">
            <summary className="text-xs font-semibold cursor-pointer">Rebalance history ({rebalLogs.length} entries)</summary>
            <div className="table-wrapper mt-1">
              <table className="data-table text-xs">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Status</th>
                    <th>Orders</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {rebalLogs.map((r) => (
                    <tr key={r.id}>
                      <td>{fmtTime(r.timestamp)}</td>
                      <td className={r.status === "SUCCESS" ? "text-emerald-600" : "text-red-500"}>{r.status}</td>
                      <td>{r.n_orders}</td>
                      <td className="text-xs max-w-[300px] truncate">{JSON.stringify(r.details)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        ) : null}
      </div>
    </main>
  );
}

