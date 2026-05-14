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
import { PaperPerformanceCharts } from "./PaperPerformanceCharts";
import { Button } from "../_components/ui/Button";
import { Card, CardContent } from "../_components/ui/Card";
import { Badge } from "../_components/ui/Badge";
import { cn } from "../_components/cn";

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

  type PaperRebalanceLeg = {
    ticker: string;
    target_weight: number;
    price: number;
    target_value: number;
    target_quantity: number;
    current_quantity: number;
    delta_quantity: number;
    side: "BUY" | "SELL";
  };
  type PaperRebalancePreview = {
    legs?: PaperRebalanceLeg[];
    allocation_amount?: number;
    estimated_cash_remaining?: number;
    as_of?: string;
    orders?: unknown[];
    trades?: unknown[];
  };

  const [pnlWindow, setPnlWindow] = useState<"7d" | "30d" | "all">("all");
  const [ordersFillsTab, setOrdersFillsTab] = useState<"orders" | "fills">("orders");

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

  const filteredPnlDaily = useMemo(() => {
    if (!pnlDaily.length) return [];
    if (pnlWindow === "all") return pnlDaily;
    const n = pnlWindow === "7d" ? 7 : 30;
    return pnlDaily.slice(-n);
  }, [pnlDaily, pnlWindow]);

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

  const preview = rebalancePreview as PaperRebalancePreview | null;
  const legs = preview?.legs || [];

  return (
    <main className="mx-auto max-w-[1400px] space-y-6 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="mb-1 mt-1 text-2xl font-semibold tracking-tight">Paper Trading</h2>
          <p className="text-sm text-muted-foreground">Simulated fills, portfolio rebalance, and performance — same view style as Backtest.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            Account
            <select
              value={accountId}
              onChange={(e) => onAccountChange(e.target.value)}
              className="input-field min-w-[200px]"
            >
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name ? `${a.name} (${a.id})` : a.id}
                </option>
              ))}
            </select>
          </label>
          <Button variant="outline" size="sm" onClick={() => refreshAll(accountId)} disabled={!!actionBusy}>
            Refresh
          </Button>
        </div>
      </div>

      {error ? <div className="error-message">{error}</div> : null}

      {/* Hero metrics from P&L summary + live balances */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="shadow-none">
          <CardContent className="py-4">
            <div className="text-xs font-medium text-muted-foreground">Total equity</div>
            <div className="mt-1 text-2xl font-bold tabular-nums">{fmtMoney(computedEquity, currency)}</div>
            <div className="mt-1 text-[11px] text-muted-foreground">Cash {fmtMoney(cash, currency)}</div>
          </CardContent>
        </Card>
        <Card className="shadow-none">
          <CardContent className="py-4">
            <div className="text-xs font-medium text-muted-foreground">Total return</div>
            <div
              className={cn(
                "mt-1 text-2xl font-bold tabular-nums",
                pnlSummary && pnlSummary.total_return >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400",
              )}
            >
              {pnlSummary && pnlSummary.days > 0 ? `${(pnlSummary.total_return * 100).toFixed(2)}%` : "—"}
            </div>
            {pnlSummary && pnlSummary.days > 0 ? (
              <Badge variant="outline" className="mt-2">
                {pnlSummary.days} days
              </Badge>
            ) : (
              <div className="mt-1 text-[11px] text-muted-foreground">Awaiting daily snapshots</div>
            )}
          </CardContent>
        </Card>
        <Card className="shadow-none">
          <CardContent className="py-4">
            <div className="text-xs font-medium text-muted-foreground">Max drawdown</div>
            <div className="mt-1 text-2xl font-bold tabular-nums text-red-600 dark:text-red-400">
              {pnlSummary && pnlSummary.days > 0 ? `${(pnlSummary.max_drawdown * 100).toFixed(2)}%` : "—"}
            </div>
            <div className="mt-1 text-[11px] text-muted-foreground">From snapshot series</div>
          </CardContent>
        </Card>
        <Card className="shadow-none">
          <CardContent className="py-4">
            <div className="text-xs font-medium text-muted-foreground">Open positions</div>
            <div className="mt-1 text-2xl font-bold tabular-nums">{positions.length}</div>
            <div className="mt-1 text-[11px] text-muted-foreground">Updated {fmtTime(balance?.updated_at)}</div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-[420px_1fr]">
        <Card className="shadow-none">
          <CardContent className="space-y-4 p-4">
            <div>
              <h3 className="mb-2 text-sm font-semibold">Fund account</h3>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  value={fundAmount}
                  onChange={(e) => setFundAmount(e.target.value)}
                  inputMode="decimal"
                  placeholder="Amount"
                  className="input-field w-36"
                />
                <span className="text-xs text-muted-foreground">{currency}</span>
                <Button onClick={onFund} disabled={actionBusy === "fund"} variant="secondary" size="sm">
                  {actionBusy === "fund" ? "Funding…" : "Add cash"}
                </Button>
              </div>
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold">Market order</h3>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                  placeholder="Symbol"
                  className="input-field w-28"
                />
                <select value={side} onChange={(e) => setSide(e.target.value as PaperOrderSide)} className="input-field w-24">
                  <option value="BUY">BUY</option>
                  <option value="SELL">SELL</option>
                </select>
                <input
                  value={qty}
                  onChange={(e) => setQty(e.target.value)}
                  inputMode="decimal"
                  placeholder="Qty"
                  className="input-field w-24"
                />
                <Button onClick={onSubmitOrder} disabled={actionBusy === "order"} size="sm">
                  {actionBusy === "order" ? "Submitting…" : "Submit"}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="shadow-none">
          <CardContent className="p-0">
            <div className="flex border-b">
              <button
                type="button"
                className={cn(
                  "flex-1 px-4 py-3 text-sm font-medium transition-colors",
                  ordersFillsTab === "orders" ? "border-b-2 border-primary bg-accent/30" : "text-muted-foreground hover:bg-accent/20",
                )}
                onClick={() => setOrdersFillsTab("orders")}
              >
                Orders ({orders.length})
              </button>
              <button
                type="button"
                className={cn(
                  "flex-1 px-4 py-3 text-sm font-medium transition-colors",
                  ordersFillsTab === "fills" ? "border-b-2 border-primary bg-accent/30" : "text-muted-foreground hover:bg-accent/20",
                )}
                onClick={() => setOrdersFillsTab("fills")}
              >
                Fills ({fills.length})
              </button>
            </div>
            <div className="table-wrapper max-h-[320px] overflow-auto">
              {ordersFillsTab === "orders" ? (
                <table className="data-table w-full">
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
                        <td className="text-xs whitespace-nowrap">{fmtTime(o.created_at)}</td>
                        <td className="font-semibold">{o.symbol}</td>
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
              ) : (
                <table className="data-table w-full">
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
                        <td className="text-xs whitespace-nowrap">{fmtTime(f.timestamp)}</td>
                        <td className="font-semibold">{f.symbol}</td>
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
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="shadow-none">
        <CardContent className="p-0">
          <div className="section-header">Positions</div>
          <div className="table-wrapper overflow-x-auto">
            <table className="data-table w-full min-w-[640px]">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Qty</th>
                  <th>Avg cost</th>
                  <th>Mkt price</th>
                  <th>Mkt value</th>
                  <th>Unrealized</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => {
                  const mv =
                    p.market_value ?? (p.market_price != null && p.quantity != null ? p.market_price * p.quantity : undefined);
                  const unreal =
                    mv != null && p.avg_cost != null && Number.isFinite(mv) && Number.isFinite(p.avg_cost) && Number.isFinite(p.quantity)
                      ? mv - p.avg_cost * p.quantity
                      : undefined;
                  const long = p.quantity > 0;
                  const short = p.quantity < 0;
                  return (
                    <tr key={p.symbol}>
                      <td className={cn("font-semibold", long && "text-emerald-600 dark:text-emerald-400", short && "text-red-600 dark:text-red-400")}>
                        {p.symbol}
                      </td>
                      <td className="font-mono text-sm">{fmtNum(p.quantity, 4)}</td>
                      <td>{fmtMoney(p.avg_cost, p.currency || currency)}</td>
                      <td>{fmtMoney(p.market_price, p.currency || currency)}</td>
                      <td>{fmtMoney(mv, p.currency || currency)}</td>
                      <td
                        className={cn(
                          "font-mono text-sm",
                          unreal != null && unreal > 0 && "text-emerald-600",
                          unreal != null && unreal < 0 && "text-red-600",
                        )}
                      >
                        {unreal != null && Number.isFinite(unreal) ? fmtMoney(unreal, p.currency || currency) : "—"}
                      </td>
                    </tr>
                  );
                })}
                {positions.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="empty-state">
                      No positions.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {portfolios.length ? (
        <Card className="shadow-none">
          <CardContent className="space-y-4 p-4">
            <h3 className="text-sm font-semibold">Rebalance to portfolio</h3>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={portfolioId}
                onChange={(e) => setPortfolioId(e.target.value)}
                className="input-field min-w-[240px]"
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
                placeholder="Allocation USD"
                className="input-field w-36"
              />
              <Button onClick={onPreviewRebalance} disabled={actionBusy === "preview"} size="sm" variant="outline">
                {actionBusy === "preview" ? "Previewing…" : "Preview"}
              </Button>
              <Button onClick={onExecuteRebalance} disabled={actionBusy === "execute"} size="sm" variant="secondary">
                {actionBusy === "execute" ? "Executing…" : "Execute"}
              </Button>
            </div>
            {rebalanceError ? <div className="error-message">{rebalanceError}</div> : null}
            {preview && (legs.length > 0 || preview.orders) ? (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                  {preview.as_of ? <span>As of {fmtTime(preview.as_of)}</span> : null}
                  {preview.allocation_amount != null ? <span>Allocation {fmtMoney(preview.allocation_amount)}</span> : null}
                  {preview.estimated_cash_remaining != null ? (
                    <span>Est. cash remaining {fmtMoney(preview.estimated_cash_remaining)}</span>
                  ) : null}
                </div>
                {legs.length > 0 ? (
                  <div className="table-wrapper overflow-x-auto rounded-md border">
                    <table className="data-table w-full min-w-[720px] text-sm">
                      <thead>
                        <tr>
                          <th>Symbol</th>
                          <th className="text-right">Current</th>
                          <th className="text-right">Target qty</th>
                          <th className="text-right">Delta</th>
                          <th>Side</th>
                          <th className="text-right">Price</th>
                          <th className="text-right">Target value</th>
                          <th className="text-right">Weight</th>
                        </tr>
                      </thead>
                      <tbody>
                        {legs.map((leg) => (
                          <tr key={leg.ticker}>
                            <td className="font-semibold">{leg.ticker}</td>
                            <td className="text-right font-mono text-xs">{fmtNum(leg.current_quantity, 4)}</td>
                            <td className="text-right font-mono text-xs">{fmtNum(leg.target_quantity, 4)}</td>
                            <td className="text-right font-mono text-xs">{fmtNum(leg.delta_quantity, 4)}</td>
                            <td>
                              <Badge variant={leg.side === "BUY" ? "success" : "danger"}>{leg.side}</Badge>
                            </td>
                            <td className="text-right font-mono text-xs">{fmtMoney(leg.price)}</td>
                            <td className="text-right font-mono text-xs">{fmtMoney(leg.target_value)}</td>
                            <td className="text-right font-mono text-xs">{(leg.target_weight * 100).toFixed(1)}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : preview.orders && Array.isArray(preview.orders) ? (
                  <p className="text-sm text-muted-foreground">Executed {preview.orders.length} orders — positions refreshed.</p>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <Card className="shadow-none">
        <CardContent className="space-y-4 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-base font-semibold">Performance</h3>
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex rounded-md border p-0.5">
                {(["7d", "30d", "all"] as const).map((w) => (
                  <button
                    key={w}
                    type="button"
                    onClick={() => setPnlWindow(w)}
                    className={cn(
                      "rounded px-2.5 py-1 text-xs font-medium",
                      pnlWindow === w ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent",
                    )}
                  >
                    {w === "all" ? "All" : w.toUpperCase()}
                  </button>
                ))}
              </div>
              <Button variant="outline" size="sm" onClick={() => refreshPnl(accountId)} disabled={pnlLoading}>
                {pnlLoading ? "Loading…" : "Refresh P&L"}
              </Button>
            </div>
          </div>

          {pnlSummary && pnlSummary.days > 0 ? (
            <>
              <div className="rounded-lg border bg-muted/10 p-2">
                <PaperPerformanceCharts daily={filteredPnlDaily} />
              </div>
              {pnlSummary.total_pnl != null ? (
                <div className="text-center text-sm text-muted-foreground">
                  Total P&amp;L{" "}
                  <span className={cn("font-semibold", pnlSummary.total_pnl >= 0 ? "text-emerald-600" : "text-red-600")}>
                    {fmtMoney(pnlSummary.total_pnl)}
                  </span>
                </div>
              ) : null}
              <details className="rounded-md border">
                <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground">
                  Daily breakdown ({pnlDaily.length} rows)
                </summary>
                <div className="table-wrapper max-h-[280px] overflow-auto border-t">
                  <table className="data-table w-full text-xs">
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
            <p className="text-sm text-muted-foreground">
              No snapshots yet. Daily snapshots (e.g. 4:30 PM ET) populate equity and risk metrics here.
            </p>
          )}

          {rebalLogs.length > 0 ? (
            <details className="rounded-md border">
              <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground">
                Rebalance history ({rebalLogs.length})
              </summary>
              <div className="table-wrapper max-h-[200px] overflow-auto border-t">
                <table className="data-table w-full text-xs">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Status</th>
                      <th>Orders</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rebalLogs.map((r) => (
                      <tr key={r.id}>
                        <td>{fmtTime(r.timestamp)}</td>
                        <td className={r.status === "SUCCESS" ? "text-emerald-600" : "text-red-500"}>{r.status}</td>
                        <td>{r.n_orders}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          ) : null}
        </CardContent>
      </Card>
    </main>
  );
}

