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
    return <div>Loading paper trading…</div>;
  }

  return (
    <main style={{ maxWidth: 1400, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: "8px 0 6px" }}>Paper Trading</h2>
          <div style={{ color: "#666", fontSize: 12 }}>Place a market order and watch cash/positions update instantly.</div>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <label style={{ fontSize: 12, color: "#666" }}>
            Account{" "}
            <select
              value={accountId}
              onChange={(e) => onAccountChange(e.target.value)}
              style={{ padding: "6px 8px", marginLeft: 6 }}
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
            style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #ddd" }}
            disabled={!!actionBusy}
          >
            Refresh
          </button>
        </div>
      </div>

      {error ? (
        <div
          style={{
            background: "#fff3f3",
            border: "1px solid #f3b0b0",
            padding: 10,
            borderRadius: 8,
            marginTop: 12,
            color: "#b00020",
          }}
        >
          {error}
        </div>
      ) : null}

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 14 }}>
        <div style={{ padding: "10px 12px", border: "1px solid #eee", borderRadius: 10 }}>
          <div style={{ fontSize: 11, color: "#666", textTransform: "uppercase" }}>Cash</div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>{fmtMoney(cash, currency)}</div>
        </div>
        <div style={{ padding: "10px 12px", border: "1px solid #eee", borderRadius: 10 }}>
          <div style={{ fontSize: 11, color: "#666", textTransform: "uppercase" }}>Equity</div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>{fmtMoney(computedEquity, currency)}</div>
        </div>
        <div style={{ padding: "10px 12px", border: "1px solid #eee", borderRadius: 10 }}>
          <div style={{ fontSize: 11, color: "#666", textTransform: "uppercase" }}>Positions</div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>{positions.length}</div>
        </div>
        <div style={{ padding: "10px 12px", border: "1px solid #eee", borderRadius: 10 }}>
          <div style={{ fontSize: 11, color: "#666", textTransform: "uppercase" }}>Last update</div>
          <div style={{ fontSize: 12, fontWeight: 600 }}>{fmtTime(balance?.updated_at)}</div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "420px 1fr", gap: 12, marginTop: 14 }}>
        <div style={{ border: "1px solid #eee", borderRadius: 12, padding: 12 }}>
          <h3 style={{ margin: "0 0 10px" }}>Fund paper account</h3>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <input
              value={fundAmount}
              onChange={(e) => setFundAmount(e.target.value)}
              inputMode="decimal"
              placeholder="Amount"
              style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #ddd", width: 160 }}
            />
            <span style={{ color: "#666", fontSize: 12 }}>{currency}</span>
            <button
              onClick={onFund}
              disabled={actionBusy === "fund"}
              style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid #ddd" }}
            >
              {actionBusy === "fund" ? "Funding…" : "Add cash"}
            </button>
          </div>
          <div style={{ marginTop: 8, fontSize: 12, color: "#666" }}>
            Uses Agent E funding endpoint if available; otherwise shows a clear error.
          </div>
        </div>

        <div style={{ border: "1px solid #eee", borderRadius: 12, padding: 12 }}>
          <h3 style={{ margin: "0 0 10px" }}>Order ticket (market)</h3>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="Symbol (e.g. AAPL)"
              style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #ddd", width: 160 }}
            />
            <select value={side} onChange={(e) => setSide(e.target.value as PaperOrderSide)} style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #ddd" }}>
              <option value="BUY">BUY</option>
              <option value="SELL">SELL</option>
            </select>
            <input
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              inputMode="decimal"
              placeholder="Qty"
              style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #ddd", width: 120 }}
            />
            <button
              onClick={onSubmitOrder}
              disabled={actionBusy === "order"}
              style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid #ddd" }}
            >
              {actionBusy === "order" ? "Submitting…" : "Submit"}
            </button>
          </div>
          <div style={{ marginTop: 8, fontSize: 12, color: "#666" }}>
            After submit, this page auto-refreshes to show the fill and updated cash/positions.
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 14 }}>
        <div style={{ border: "1px solid #eee", borderRadius: 12, overflow: "hidden" }}>
          <div style={{ padding: 10, background: "#fafafa", borderBottom: "1px solid #eee", fontWeight: 600 }}>Positions</div>
          <div style={{ overflow: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ textAlign: "left", fontSize: 12, color: "#666" }}>
                  <th style={{ padding: "10px 12px", borderBottom: "1px solid #eee" }}>Symbol</th>
                  <th style={{ padding: "10px 12px", borderBottom: "1px solid #eee" }}>Qty</th>
                  <th style={{ padding: "10px 12px", borderBottom: "1px solid #eee" }}>Avg cost</th>
                  <th style={{ padding: "10px 12px", borderBottom: "1px solid #eee" }}>Mkt price</th>
                  <th style={{ padding: "10px 12px", borderBottom: "1px solid #eee" }}>Mkt value</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={p.symbol} style={{ borderBottom: "1px solid #f3f3f3" }}>
                    <td style={{ padding: "10px 12px", fontWeight: 700 }}>{p.symbol}</td>
                    <td style={{ padding: "10px 12px" }}>{fmtNum(p.quantity, 4)}</td>
                    <td style={{ padding: "10px 12px" }}>{fmtMoney(p.avg_cost, p.currency || currency)}</td>
                    <td style={{ padding: "10px 12px" }}>{fmtMoney(p.market_price, p.currency || currency)}</td>
                    <td style={{ padding: "10px 12px" }}>
                      {fmtMoney(p.market_value ?? (p.market_price != null ? p.market_price * p.quantity : undefined), p.currency || currency)}
                    </td>
                  </tr>
                ))}
                {positions.length === 0 ? (
                  <tr>
                    <td colSpan={5} style={{ padding: 12, color: "#666" }}>
                      No positions.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>

        <div style={{ border: "1px solid #eee", borderRadius: 12, overflow: "hidden" }}>
          <div style={{ padding: 10, background: "#fafafa", borderBottom: "1px solid #eee", fontWeight: 600 }}>Recent fills / trades</div>
          <div style={{ overflow: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ textAlign: "left", fontSize: 12, color: "#666" }}>
                  <th style={{ padding: "10px 12px", borderBottom: "1px solid #eee" }}>Time</th>
                  <th style={{ padding: "10px 12px", borderBottom: "1px solid #eee" }}>Symbol</th>
                  <th style={{ padding: "10px 12px", borderBottom: "1px solid #eee" }}>Side</th>
                  <th style={{ padding: "10px 12px", borderBottom: "1px solid #eee" }}>Qty</th>
                  <th style={{ padding: "10px 12px", borderBottom: "1px solid #eee" }}>Price</th>
                </tr>
              </thead>
              <tbody>
                {fills.map((f, idx) => (
                  <tr key={`${f.id ?? "fill"}-${idx}`} style={{ borderBottom: "1px solid #f3f3f3" }}>
                    <td style={{ padding: "10px 12px", fontSize: 12, color: "#444" }}>{fmtTime(f.timestamp)}</td>
                    <td style={{ padding: "10px 12px", fontWeight: 700 }}>{f.symbol}</td>
                    <td style={{ padding: "10px 12px" }}>{f.side}</td>
                    <td style={{ padding: "10px 12px" }}>{fmtNum(f.quantity, 4)}</td>
                    <td style={{ padding: "10px 12px" }}>{fmtMoney(f.price, currency)}</td>
                  </tr>
                ))}
                {fills.length === 0 ? (
                  <tr>
                    <td colSpan={5} style={{ padding: 12, color: "#666" }}>
                      No fills yet.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 14, border: "1px solid #eee", borderRadius: 12, overflow: "hidden" }}>
        <div style={{ padding: 10, background: "#fafafa", borderBottom: "1px solid #eee", fontWeight: 600 }}>Recent orders</div>
        <div style={{ overflow: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", fontSize: 12, color: "#666" }}>
                <th style={{ padding: "10px 12px", borderBottom: "1px solid #eee" }}>Time</th>
                <th style={{ padding: "10px 12px", borderBottom: "1px solid #eee" }}>Symbol</th>
                <th style={{ padding: "10px 12px", borderBottom: "1px solid #eee" }}>Side</th>
                <th style={{ padding: "10px 12px", borderBottom: "1px solid #eee" }}>Qty</th>
                <th style={{ padding: "10px 12px", borderBottom: "1px solid #eee" }}>Type</th>
                <th style={{ padding: "10px 12px", borderBottom: "1px solid #eee" }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o, idx) => (
                <tr key={`${o.id ?? "order"}-${idx}`} style={{ borderBottom: "1px solid #f3f3f3" }}>
                  <td style={{ padding: "10px 12px", fontSize: 12, color: "#444" }}>{fmtTime(o.created_at)}</td>
                  <td style={{ padding: "10px 12px", fontWeight: 700 }}>{o.symbol}</td>
                  <td style={{ padding: "10px 12px" }}>{o.side}</td>
                  <td style={{ padding: "10px 12px" }}>{fmtNum(o.quantity, 4)}</td>
                  <td style={{ padding: "10px 12px" }}>{o.type || "—"}</td>
                  <td style={{ padding: "10px 12px" }}>{o.status || "—"}</td>
                </tr>
              ))}
              {orders.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: 12, color: "#666" }}>
                    No orders yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      {portfolios.length ? (
        <div style={{ marginTop: 14, border: "1px solid #eee", borderRadius: 12, padding: 12 }}>
          <h3 style={{ margin: "0 0 10px" }}>Optional: Allocate cash to a portfolio (rebalance)</h3>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <select
              value={portfolioId}
              onChange={(e) => setPortfolioId(e.target.value)}
              style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #ddd", minWidth: 260 }}
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
              style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #ddd", width: 200 }}
            />
            <button
              onClick={onPreviewRebalance}
              disabled={actionBusy === "preview"}
              style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid #ddd" }}
            >
              {actionBusy === "preview" ? "Previewing…" : "Preview"}
            </button>
            <button
              onClick={onExecuteRebalance}
              disabled={actionBusy === "execute"}
              style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid #ddd" }}
            >
              {actionBusy === "execute" ? "Executing…" : "Execute"}
            </button>
          </div>
          {rebalanceError ? (
            <div style={{ marginTop: 10, color: "#b00020", fontSize: 12 }}>
              {rebalanceError}
            </div>
          ) : null}
          {rebalancePreview ? (
            <pre style={{ marginTop: 10, background: "#f6f6f6", padding: 12, overflow: "auto", borderRadius: 10 }}>
              {JSON.stringify(rebalancePreview, null, 2)}
            </pre>
          ) : null}
        </div>
      ) : null}
    </main>
  );
}

